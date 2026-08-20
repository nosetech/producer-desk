"""orchestrator.github_client の単体テスト。gh CLI呼び出しはフェイクに差し替える。"""

from __future__ import annotations

import json
import subprocess

from orchestrator.aggregation import IssueSummary
from orchestrator.github_client import (
    BOT_COMMENT_MARKER,
    close_issue,
    delete_branch,
    get_pr_branch,
    list_issues,
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


def test_resolve_pr_number_finds_cross_referenced_pull_request() -> None:
    fake_run = _fake_run_raw(
        [
            {"event": "labeled"},
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 33, "pull_request": {"url": "..."}}},
            },
        ]
    )

    assert resolve_pr_number("nosetech/project-a", 30, run=fake_run) == 33
    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == ["gh", "api", "repos/nosetech/project-a/issues/30/timeline"]


def test_resolve_pr_number_ignores_cross_referenced_issues_without_pull_request() -> None:
    fake_run = _fake_run_raw(
        [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 40, "pull_request": None}},
            },
        ]
    )

    assert resolve_pr_number("nosetech/project-a", 30, run=fake_run) is None


def test_resolve_pr_number_returns_latest_when_multiple_linked() -> None:
    fake_run = _fake_run_raw(
        [
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 33, "pull_request": {"url": "..."}}},
            },
            {
                "event": "cross-referenced",
                "source": {"issue": {"number": 40, "pull_request": {"url": "..."}}},
            },
        ]
    )

    assert resolve_pr_number("nosetech/project-a", 30, run=fake_run) == 40


def test_resolve_pr_number_returns_none_when_no_events() -> None:
    fake_run = _fake_run_raw([])

    assert resolve_pr_number("nosetech/project-a", 30, run=fake_run) is None


def _fake_run_dispatch(responses: dict[str, object]) -> object:
    """呼び出すgh subcommand（`timeline`/`pr list`）に応じて異なるレスポンスを返すフェイク。"""
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        key = "timeline" if "timeline" in cmd[2] else "pr_list"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(responses[key]), stderr=""
        )

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_resolve_pr_number_falls_back_to_open_pr_search_when_no_cross_reference() -> None:
    """issue #82の再発防止テスト。

    issue番号の直後にCJK文字が続く（`#77で`のような）記法だとGitHub側の自動
    リンク解析がissue参照として認識せず、cross-referenceイベントが生成されない
    ことがある。その場合でもOPEN PR本文検索でPRを解決できることを確認する。
    """
    fake_run = _fake_run_dispatch(
        {
            "timeline": [],
            "pr_list": [
                {
                    "number": 81,
                    "title": "fix: 判断待ちの不具合を修正する",
                    "body": "issue #77で報告された不具合を修正しました。",
                    "updatedAt": "2026-08-10T00:00:00Z",
                }
            ],
        }
    )

    assert resolve_pr_number("nosetech/project-a", 77, run=fake_run) == 81
    [timeline_cmd, pr_list_cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert timeline_cmd == ["gh", "api", "repos/nosetech/project-a/issues/77/timeline"]
    assert pr_list_cmd == [
        "gh",
        "pr",
        "list",
        "--repo",
        "nosetech/project-a",
        "--state",
        "open",
        "--json",
        "number,title,body,updatedAt",
    ]


def test_resolve_pr_number_fallback_avoids_matching_longer_issue_numbers() -> None:
    """`#770`のような別issue番号への誤マッチを避けることを確認する。"""
    fake_run = _fake_run_dispatch(
        {
            "timeline": [],
            "pr_list": [
                {
                    "number": 90,
                    "title": "無関係な変更",
                    "body": "issue #770について対応",
                    "updatedAt": "2026-08-10T00:00:00Z",
                }
            ],
        }
    )

    assert resolve_pr_number("nosetech/project-a", 77, run=fake_run) is None


def test_resolve_pr_number_fallback_returns_none_when_no_match() -> None:
    fake_run = _fake_run_dispatch({"timeline": [], "pr_list": []})

    assert resolve_pr_number("nosetech/project-a", 77, run=fake_run) is None


def test_resolve_pr_number_fallback_returns_most_recently_updated_when_multiple_match() -> None:
    fake_run = _fake_run_dispatch(
        {
            "timeline": [],
            "pr_list": [
                {
                    "number": 81,
                    "title": "古い方の対応",
                    "body": "issue #77で報告された不具合を修正",
                    "updatedAt": "2026-08-08T00:00:00Z",
                },
                {
                    "number": 85,
                    "title": "新しい方の対応",
                    "body": "issue #77で報告された不具合を再修正",
                    "updatedAt": "2026-08-10T00:00:00Z",
                },
            ],
        }
    )

    assert resolve_pr_number("nosetech/project-a", 77, run=fake_run) == 85


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
