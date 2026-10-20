"""orchestrator.github_client の単体テスト。gh CLI呼び出しはフェイクに差し替える。"""

from __future__ import annotations

import json
import subprocess

from orchestrator.aggregation import IssueSummary, PrCandidate
from orchestrator.github_client import (
    BOT_COMMENT_MARKER,
    close_issue,
    delete_branch,
    get_pr_branch,
    get_pr_status_check_rollup,
    list_issues,
    list_linked_prs,
    merge_pr,
    post_comment,
    resolve_pr_number,
)


def _fake_run(stdout_issues: list[dict]) -> object:
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(stdout_issues), stderr=""
        )

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _fake_run_raw(stdout: object) -> object:
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(stdout), stderr=""
        )

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_list_issues_parses_gh_output_into_issue_summaries() -> None:
    fake_run = _fake_run(
        [
            {
                "number": 12,
                "title": "ログイン機能のAPI設計について",
                "labels": [{"name": "needs-human-decision"}],
                "comments": [{"body": "承認します。"}],
                "updatedAt": "2026-08-03T05:27:16Z",
                "state": "OPEN",
            }
        ]
    )

    result = list_issues("nosetech/project-a", run=fake_run)

    assert result == [
        IssueSummary(
            repo="nosetech/project-a",
            number=12,
            title="ログイン機能のAPI設計について",
            labels=["needs-human-decision"],
            comments=[{"body": "承認します。"}],
            updated_at="2026-08-03T05:27:16Z",
            state="OPEN",
        )
    ]


def test_list_issues_parses_closed_state() -> None:
    fake_run = _fake_run(
        [
            {
                "number": 5,
                "title": "完了したタスク",
                "labels": [{"name": "status:closed"}],
                "comments": [],
                "updatedAt": "2026-08-04T00:00:00Z",
                "state": "CLOSED",
            }
        ]
    )

    result = list_issues("nosetech/project-a", run=fake_run)

    assert result[0].state == "CLOSED"


def test_list_issues_calls_gh_with_expected_arguments() -> None:
    fake_run = _fake_run([])

    list_issues("nosetech/project-a", run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == [
        "gh",
        "issue",
        "list",
        "--repo",
        "nosetech/project-a",
        "--state",
        "all",
        "--json",
        "number,title,labels,comments,updatedAt,state",
        "--limit",
        "100",
    ]


def test_list_issues_returns_empty_list_when_no_issues() -> None:
    fake_run = _fake_run([])

    assert list_issues("nosetech/project-a", run=fake_run) == []


def test_post_comment_appends_bot_marker() -> None:
    fake_run = _fake_run([])

    post_comment("nosetech/project-a", 12, "Agent Runner実行結果:\n完了しました", run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd[:4] == ["gh", "api", "repos/nosetech/project-a/issues/12/comments", "-f"]
    posted_body = cmd[4].removeprefix("body=")
    assert posted_body.startswith("Agent Runner実行結果:\n完了しました")
    assert BOT_COMMENT_MARKER in posted_body


def _pr(number: int, *, body: str = "", closing: list[int] | None = None, **extra: object) -> dict:
    return {
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/nosetech/project-a/pull/{number}",
        "isDraft": False,
        "headRefName": f"feature/{number}",
        "baseRefName": "develop",
        "body": body,
        "closingIssuesReferences": [{"number": n} for n in (closing or [])],
        **extra,
    }


def test_list_linked_prs_calls_gh_pr_list_for_open_prs() -> None:
    fake_run = _fake_run_raw([])

    assert list_linked_prs("nosetech/project-a", 30, run=fake_run) == []
    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == [
        "gh",
        "pr",
        "list",
        "--repo",
        "nosetech/project-a",
        "--state",
        "open",
        "--json",
        "number,title,url,isDraft,headRefName,baseRefName,body,closingIssuesReferences",
        "--limit",
        "100",
    ]


def test_list_linked_prs_selects_closing_pr_over_mention_only_pr() -> None:
    """issue #206: `Closes #N`のPRは対応PR、言及だけのPRは候補にしない。"""
    fake_run = _fake_run_raw(
        [
            _pr(40, body="#30 の後続の修正です（言及のみ）"),
            _pr(33, body="対応しました\n\nCloses #30"),
        ]
    )

    candidates = list_linked_prs("nosetech/project-a", 30, run=fake_run)

    assert [c.number for c in candidates] == [33]
    assert candidates[0] == PrCandidate(
        number=33,
        title="PR 33",
        url="https://github.com/nosetech/project-a/pull/33",
        is_draft=False,
        head_ref_name="feature/33",
        base_ref_name="develop",
    )


def test_list_linked_prs_uses_closing_issues_references() -> None:
    fake_run = _fake_run_raw([_pr(33, closing=[30]), _pr(34, closing=[31])])

    candidates = list_linked_prs("nosetech/project-a", 30, run=fake_run)

    assert [c.number for c in candidates] == [33]


def test_list_linked_prs_matches_closing_keyword_followed_by_cjk() -> None:
    """issue #82: `#77で`のようにCJK文字が直後に続いても本文検索で検出できる。"""
    fake_run = _fake_run_raw([_pr(81, body="Closes #77で報告された不具合の修正")])

    assert [c.number for c in list_linked_prs("nosetech/project-a", 77, run=fake_run)] == [81]


def test_list_linked_prs_avoids_matching_longer_issue_numbers() -> None:
    fake_run = _fake_run_raw([_pr(90, body="Closes #770")])

    assert list_linked_prs("nosetech/project-a", 77, run=fake_run) == []


def test_list_linked_prs_returns_all_closing_prs_when_multiple() -> None:
    fake_run = _fake_run_raw([_pr(85, body="Fixes #77"), _pr(81, body="closes #77")])

    candidates = list_linked_prs("nosetech/project-a", 77, run=fake_run)

    assert [c.number for c in candidates] == [85, 81]


def test_resolve_pr_number_returns_number_only_when_unique() -> None:
    assert (
        resolve_pr_number("nosetech/project-a", 30, run=_fake_run_raw([_pr(33, body="Closes #30")]))
        == 33
    )
    ambiguous = _fake_run_raw([_pr(33, body="Closes #30"), _pr(40, body="Closes #30")])
    assert resolve_pr_number("nosetech/project-a", 30, run=ambiguous) is None
    assert resolve_pr_number("nosetech/project-a", 30, run=_fake_run_raw([])) is None


def test_merge_pr_calls_gh_pr_merge_squash() -> None:
    fake_run = _fake_run_raw({})

    merge_pr("nosetech/project-a", 33, run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == ["gh", "pr", "merge", "--squash", "--repo", "nosetech/project-a", "33"]


def test_close_issue_calls_gh_issue_close() -> None:
    fake_run = _fake_run_raw({})

    close_issue("nosetech/project-a", 58, run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == ["gh", "issue", "close", "--repo", "nosetech/project-a", "58"]


def test_get_pr_branch_returns_head_ref() -> None:
    fake_run = _fake_run_raw({"head": {"ref": "feature/issue-72-delete-branch"}})

    result = get_pr_branch("nosetech/project-a", 33, run=fake_run)

    assert result == "feature/issue-72-delete-branch"
    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == ["gh", "api", "repos/nosetech/project-a/pulls/33"]


def test_get_pr_status_check_rollup_returns_rollup_list() -> None:
    """issue #173: orchestrator.ci_watcherがCI完了判定に使う取得関数。"""
    fake_run = _fake_run_raw(
        {"statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]}
    )

    result = get_pr_status_check_rollup("nosetech/project-a", 172, run=fake_run)

    assert result == [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == [
        "gh",
        "pr",
        "view",
        "172",
        "--repo",
        "nosetech/project-a",
        "--json",
        "statusCheckRollup",
    ]


def test_get_pr_status_check_rollup_returns_empty_list_when_no_checks_configured() -> None:
    fake_run = _fake_run_raw({"statusCheckRollup": None})

    result = get_pr_status_check_rollup("nosetech/project-a", 172, run=fake_run)

    assert result == []


def test_delete_branch_calls_gh_api_delete_ref() -> None:
    fake_run = _fake_run_raw({})

    delete_branch("nosetech/project-a", "feature/issue-72-delete-branch", run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == [
        "gh",
        "api",
        "-X",
        "DELETE",
        "repos/nosetech/project-a/git/refs/heads/feature/issue-72-delete-branch",
    ]


def _version_run(stdout: str):
    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    return run


def test_gh_supports_attach_by_version() -> None:
    from orchestrator.github_client import gh_supports_attach

    assert gh_supports_attach(run=_version_run("gh version 2.102.0 (2026-01-01)\n")) is True
    assert gh_supports_attach(run=_version_run("gh version 2.99.0 (2026-01-01)\n")) is True
    assert gh_supports_attach(run=_version_run("gh version 2.98.9 (2026-01-01)\n")) is False
    assert gh_supports_attach(run=_version_run("unexpected")) is None


def test_gh_supports_attach_returns_none_when_gh_missing() -> None:
    from orchestrator.github_client import gh_supports_attach

    def run(cmd, **kwargs):
        raise FileNotFoundError

    assert gh_supports_attach(run=run) is None
