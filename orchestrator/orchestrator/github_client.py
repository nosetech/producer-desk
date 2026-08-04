"""`gh` CLI経由でのOpen issue一覧取得。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from orchestrator.aggregation import IssueSummary

ISSUE_LIST_FIELDS = "number,title,labels,comments,updatedAt"

RunFn = Callable[..., subprocess.CompletedProcess[str]]


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
