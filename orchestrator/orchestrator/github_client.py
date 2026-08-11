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
ResolvePrNumberFn = Callable[[str, int], int | None]
MergePrFn = Callable[[str, int], None]
CloseIssueFn = Callable[[str, int], None]
GetPrBranchFn = Callable[[str, int], str]
DeleteBranchFn = Callable[[str, str], None]


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


def resolve_pr_number(repo: str, issue_number: int, *, run: RunFn = subprocess.run) -> int | None:
    """issueに紐づく（`Closes #`等でリンクされた）PR番号を解決する。

    `gh api repos/{repo}/issues/{issue_number}/timeline` のタイムラインイベントのうち、
    `event == "cross-referenced"` かつ `source.issue.pull_request` が存在するものを
    issueへリンクされたPRとみなす（issue #58）。複数紐づく場合は最後（最新）のものを採用する。
    見つからない場合は`None`を返す。
    """
    result = run(
        ["gh", "api", f"repos/{repo}/issues/{issue_number}/timeline"],
        capture_output=True,
        text=True,
        check=True,
    )
    events = json.loads(result.stdout)
    pr_numbers = [
        event["source"]["issue"]["number"]
        for event in events
        if event.get("event") == "cross-referenced"
        and event.get("source", {}).get("issue", {}).get("pull_request") is not None
    ]
    return pr_numbers[-1] if pr_numbers else None


def merge_pr(repo: str, pr_number: int, *, run: RunFn = subprocess.run) -> None:
    """PRをsquash mergeする（`gh pr merge --squash --repo {repo} {pr_number}`）。"""
    run(
        ["gh", "pr", "merge", "--squash", "--repo", repo, str(pr_number)],
        capture_output=True,
        text=True,
        check=True,
    )


def get_pr_branch(repo: str, pr_number: int, *, run: RunFn = subprocess.run) -> str:
    """PRのheadブランチ名を取得する（`gh api repos/{repo}/pulls/{pr_number}`のhead.ref）。"""
    result = run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["head"]["ref"]


def delete_branch(repo: str, branch: str, *, run: RunFn = subprocess.run) -> None:
    """ブランチを削除する（`gh api -X DELETE repos/{repo}/git/refs/heads/{branch}`）。

    squash merge済みPRのheadブランチの後始末として、レビュー承認時のマージ・issueクローズ
    成功後に呼び出される想定（issue #72）。この処理自体の失敗（保護ブランチ設定・既に削除済み
    等）は呼び出し元（instruct.py）で握りつぶされ、マージ・issueクローズの成功には影響しない。
    """
    run(
        ["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    )


def close_issue(repo: str, issue_number: int, *, run: RunFn = subprocess.run) -> None:
    """issueを明示的にクローズする（`gh issue close --repo {repo} {issue_number}`）。

    PR本文の`Closes #<issue番号>`によるGitHubの自動クローズは、そのPRが
    リポジトリの**デフォルトブランチ**にマージされた場合にのみ発動する。本プロジェクトの
    ワークフローはPRを`develop`（デフォルトブランチは`master`）にマージするため自動クローズが
    発動せず、issueが開いたまま残る不具合が確認された（issue #58）。そのためレビュー承認時の
    squash merge成功後は、GitHub側の自動クローズに依存せずここで明示的にクローズする。
    """
    run(
        ["gh", "issue", "close", "--repo", repo, str(issue_number)],
        capture_output=True,
        text=True,
        check=True,
    )
