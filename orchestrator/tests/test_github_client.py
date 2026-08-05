"""orchestrator.github_client の単体テスト。gh CLI呼び出しはフェイクに差し替える。"""

from __future__ import annotations

import json
import subprocess

from orchestrator.aggregation import IssueSummary
from orchestrator.github_client import BOT_COMMENT_MARKER, list_open_issues, post_comment


def _fake_run(stdout_issues: list[dict]) -> object:
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=json.dumps(stdout_issues), stderr=""
        )

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_list_open_issues_parses_gh_output_into_issue_summaries() -> None:
    fake_run = _fake_run(
        [
            {
                "number": 12,
                "title": "ログイン機能のAPI設計について",
                "labels": [{"name": "needs-human-decision"}],
                "comments": [{"body": "承認します。"}],
                "updatedAt": "2026-08-03T05:27:16Z",
            }
        ]
    )

    result = list_open_issues("nosetech/project-a", run=fake_run)

    assert result == [
        IssueSummary(
            repo="nosetech/project-a",
            number=12,
            title="ログイン機能のAPI設計について",
            labels=["needs-human-decision"],
            comments=[{"body": "承認します。"}],
            updated_at="2026-08-03T05:27:16Z",
        )
    ]


def test_list_open_issues_calls_gh_with_expected_arguments() -> None:
    fake_run = _fake_run([])

    list_open_issues("nosetech/project-a", run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd == [
        "gh",
        "issue",
        "list",
        "--repo",
        "nosetech/project-a",
        "--state",
        "open",
        "--json",
        "number,title,labels,comments,updatedAt",
    ]


def test_list_open_issues_returns_empty_list_when_no_open_issues() -> None:
    fake_run = _fake_run([])

    assert list_open_issues("nosetech/project-a", run=fake_run) == []


def test_post_comment_appends_bot_marker() -> None:
    fake_run = _fake_run([])

    post_comment("nosetech/project-a", 12, "Agent Runner実行結果:\n完了しました", run=fake_run)

    [cmd] = fake_run.calls  # type: ignore[attr-defined]
    assert cmd[:4] == ["gh", "api", "repos/nosetech/project-a/issues/12/comments", "-f"]
    posted_body = cmd[4].removeprefix("body=")
    assert posted_body.startswith("Agent Runner実行結果:\n完了しました")
    assert BOT_COMMENT_MARKER in posted_body
