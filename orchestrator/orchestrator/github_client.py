"""`gh` CLI経由でのissue一覧取得・コメント投稿・issue作成。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））・2-3（指示出しAPI共通仕様）
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from orchestrator.aggregation import IssueSummary

ISSUE_LIST_FIELDS = "number,title,labels,comments,updatedAt,state"

# 1リポジトリあたりの取得件数上限（docs/basic-design.md 2-2）。
# クローズ済みissueも活動ログに表示するための --state all 取得と合わせ、
# プロデューサー1名・3〜5プロジェクト同時進行というMVPの規模で十分な簡易的な上限。
ISSUE_LIST_LIMIT = 100

# オーケストレータ自身が投稿したコメントであることを示す不可視マーカー。
# comment_watcher（docs/basic-design.md 2-3「共通仕様」）が自分自身の投稿
# （Agent Runnerの実行結果報告、承認/却下の定型文コメント等）を新規の人間指示
# と誤検知し、無限に再ディスパッチし続けるのを防ぐために付与する
# （HTMLコメントのためissue本文上には表示されない）。
BOT_COMMENT_MARKER = "<!-- producer-desk:bot-comment -->"

RunFn = Callable[..., subprocess.CompletedProcess[str]]
PostCommentFn = Callable[[str, int, str], None]
CreateIssueFn = Callable[[str, str, str], int]


def list_issues(repo: str, *, run: RunFn = subprocess.run) -> list[IssueSummary]:
    """対象リポジトリのissue一覧（Open・Closed双方）を取得する。

    `gh issue list --state all --json number,title,labels,comments,updatedAt,state
    --limit 100` 相当。クローズ済みissueも含めて取得することで、クローズ検知による
    `status:closed` への遷移（close_watcher.py）・活動ログでの「完了」表示
    （docs/basic-design.md 2-2）を可能にする。
    """
    result = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--json",
            ISSUE_LIST_FIELDS,
            "--limit",
            str(ISSUE_LIST_LIMIT),
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
            state=issue["state"],
        )
        for issue in raw_issues
    ]


def post_comment(repo: str, issue_number: int, body: str, *, run: RunFn = subprocess.run) -> None:
    """issueにコメントを投稿する（`gh api repos/{repo}/issues/{issue_number}/comments`）。

    投稿本文には `BOT_COMMENT_MARKER` を付与する（comment_watcherによる誤検知防止）。
    """
    marked_body = f"{body}\n\n{BOT_COMMENT_MARKER}"
    run(
        ["gh", "api", f"repos/{repo}/issues/{issue_number}/comments", "-f", f"body={marked_body}"],
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
