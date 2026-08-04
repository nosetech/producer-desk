"""`gh` CLI経由でのOpen issue一覧取得・コメント投稿・issue作成。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））・2-3（指示出しAPI共通仕様）
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from orchestrator.aggregation import IssueSummary

ISSUE_LIST_FIELDS = "number,title,labels,comments,updatedAt"

RunFn = Callable[..., subprocess.CompletedProcess[str]]
PostCommentFn = Callable[[str, int, str], None]
CreateIssueFn = Callable[[str, str, str], int]


def list_open_issues(repo: str, *, run: RunFn = subprocess.run) -> list[IssueSummary]:
    """対象リポジトリのOpen issue一覧を取得する。

    `gh issue list --json number,title,labels,comments,updatedAt` 相当。
    """
    result = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            ISSUE_LIST_FIELDS,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    raw_issues = json.loads(result.stdout)

    return [
        IssueSummary(
            repo=repo,
            number=issue["number"],
            title=issue["title"],
            labels=[label["name"] for label in issue["labels"]],
            comments=issue["comments"],
            updated_at=issue["updatedAt"],
        )
        for issue in raw_issues
    ]


def post_comment(repo: str, issue_number: int, body: str, *, run: RunFn = subprocess.run) -> None:
    """issueにコメントを投稿する（`gh api repos/{repo}/issues/{issue_number}/comments`）。"""
    run(
        ["gh", "api", f"repos/{repo}/issues/{issue_number}/comments", "-f", f"body={body}"],
        capture_output=True,
        text=True,
        check=True,
    )


def create_issue(repo: str, title: str, body: str, *, run: RunFn = subprocess.run) -> int:
    """issueを作成し、issue番号を返す（`gh api repos/{repo}/issues`）。"""
    result = run(
        ["gh", "api", f"repos/{repo}/issues", "-f", f"title={title}", "-f", f"body={body}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["number"]
