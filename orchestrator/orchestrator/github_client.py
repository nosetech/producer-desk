"""`gh` CLI経由でのissue一覧取得・コメント投稿・issue作成。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））・2-3（指示出しAPI共通仕様）
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable

from orchestrator.aggregation import IssueSummary, PrCandidate

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
ListLinkedPrsFn = Callable[[str, int], list[PrCandidate]]
MergePrFn = Callable[[str, int], None]
CloseIssueFn = Callable[[str, int], None]
GetPrBranchFn = Callable[[str, int], str]
DeleteBranchFn = Callable[[str, str], None]
GetCurrentBranchFn = Callable[[str], str]
FindOpenPrByBranchFn = Callable[[str, str], dict | None]
AppendPrIssueReferenceFn = Callable[[str, int, int, str], None]
GetPrStatusCheckRollupFn = Callable[[str, int], list[dict]]


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


# PR本文の「closeする意図」を示すキーワード（GitHubのclosing keywords）。直後の`#N`が
# 数字で続く場合（`#770`等）は別issueへの参照のため除外する。`#77で`のような日本語
# 直後の参照（issue #82のCJK境界問題）でもマッチさせるため、本文を直接検索する。
_CLOSING_KEYWORD_PATTERN = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#{issue_number}(?!\d)"

LINKED_PR_LIST_FIELDS = (
    "number,title,url,isDraft,headRefName,baseRefName,body,closingIssuesReferences"
)
LINKED_PR_LIST_LIMIT = 100


def list_linked_prs(
    repo: str, issue_number: int, *, run: RunFn = subprocess.run
) -> list[PrCandidate]:
    """issueの「対応PR」（そのissueをcloseする意図のOPEN PR）候補を返す（issue #206）。

    対象リポジトリのOPEN PR一覧のうち、次のいずれかを満たすものを候補とする。
    - GraphQLの`closingIssuesReferences`（PR→closeされるissue）に当該issueが含まれる
    - PR本文に`Closes|Fixes|Resolves #N`（直後が数字でない）が含まれる
      （issue #82のCJK境界問題でGitHub側の参照解析が効かないケースの補完）

    単にPR本文・コメントで`#N`に言及しただけのPR（`cross-referenced`イベントの
    発生源になるが対応PRとは限らない）や、マージ済み・クローズ済みPRは含めない。
    返り値の順序は`gh pr list`の順（作成の新しい順）。
    """
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            LINKED_PR_LIST_FIELDS,
            "--limit",
            str(LINKED_PR_LIST_LIMIT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    closing_pattern = re.compile(
        _CLOSING_KEYWORD_PATTERN.format(issue_number=issue_number), re.IGNORECASE
    )
    candidates: list[PrCandidate] = []
    for pr in json.loads(result.stdout):
        closing_numbers = {ref.get("number") for ref in pr.get("closingIssuesReferences") or []}
        if issue_number not in closing_numbers and not closing_pattern.search(pr.get("body") or ""):
            continue
        candidates.append(
            PrCandidate(
                number=pr["number"],
                title=pr.get("title", ""),
                url=pr.get("url", ""),
                is_draft=bool(pr.get("isDraft", False)),
                head_ref_name=pr.get("headRefName", ""),
                base_ref_name=pr.get("baseRefName", ""),
            )
        )
    return candidates


def resolve_pr_number(repo: str, issue_number: int, *, run: RunFn = subprocess.run) -> int | None:
    """issueの対応PRを一意に特定できる場合のみ、そのPR番号を返す（issue #206）。

    `list_linked_prs`の候補がちょうど1件ならその番号、0件または2件以上なら`None`。
    以前の「最後のcross-referenceを採用」「`updatedAt`最新を採用」は誤ったPRを
    選びうるため廃止した。複数候補の扱い（ユーザー選択）は呼び出し元が
    `list_linked_prs`の候補一覧を使って行う。
    """
    candidates = list_linked_prs(repo, issue_number, run=run)
    if len(candidates) == 1:
        return candidates[0].number
    return None


def get_current_branch(worktree_path: str, *, run: RunFn = subprocess.run) -> str:
    """worktreeのカレントブランチ名を取得する。

    `git -C {worktree_path} rev-parse --abbrev-ref HEAD`相当。`resolve_pr_number`が
    解決できなかった場合のフォールバック（issue #144）で、Agent Runnerセッション
    終了時点のworktreeのカレントブランチをPR特定の手がかりとして使う。
    """
    result = run(
        ["git", "-C", worktree_path, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def find_open_pr_by_branch(repo: str, branch: str, *, run: RunFn = subprocess.run) -> dict | None:
    """指定ブランチをheadとするOPEN PRを検索する（issue #144）。

    `gh pr list --head {branch} --state open --json number,body`相当。1ブランチにつき
    OPEN PRは高々1件のはずという運用上の前提（`docs/basic-design.md`の開発ワークフロー）
    のため、0件または複数件ヒットした場合は一意に特定できないとみなし`None`を返す。
    """
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,body",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    prs = json.loads(result.stdout)
    if len(prs) != 1:
        return None
    return prs[0]


def append_pr_issue_reference(
    repo: str,
    pr_number: int,
    issue_number: int,
    existing_body: str,
    *,
    run: RunFn = subprocess.run,
) -> None:
    """PR本文の末尾に`Closes #<issue番号>`を追記する（issue #144）。

    既存本文をまるごと上書きするのではなく末尾に追記する。これによりGitHub側の
    cross-referenceイベントが新たに生成され、以降のポーリングでは通常の
    `resolve_pr_number`の解決経路（cross-referenceイベント方式）でも解決できるようになる。
    """
    new_body = f"{existing_body}\n\nCloses #{issue_number}"
    run(
        ["gh", "pr", "edit", str(pr_number), "--repo", repo, "--body", new_body],
        capture_output=True,
        text=True,
        check=True,
    )


def get_pr_status_check_rollup(
    repo: str, pr_number: int, *, run: RunFn = subprocess.run
) -> list[dict]:
    """PRのCIチェック結果一覧を取得する（`gh pr view --json statusCheckRollup`）。

    issue #173: `orchestrator.ci_watcher`がCI完了待機中のissueについて、対象PRの
    CIが完了したかどうかをポーリングで確認するために使う。返り値の各要素は
    GitHub Checks API由来（`status`: `QUEUED`/`IN_PROGRESS`/`COMPLETED`等）と、
    レガシーなCommit Status API由来（`state`: `PENDING`/`SUCCESS`/`FAILURE`等）の
    いずれかの形を取り得る（`gh`のGraphQLクエリがcheck run/status contextを
    区別せず同一フィールドに混在させて返すため）。`statusCheckRollup`が存在しない
    （CIが1件も設定されていない）場合は空リストを返す。
    """
    result = run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "statusCheckRollup"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    rollup = data.get("statusCheckRollup")
    return rollup if isinstance(rollup, list) else []


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


# `gh issue comment --attach`（issue #218）が使える最小バージョン。
GH_ATTACH_MIN_VERSION = (2, 99, 0)


def gh_supports_attach(*, run: RunFn = subprocess.run) -> bool | None:
    """実行ホストの`gh`が`--attach`に対応するバージョンか。バージョンを判定できなければNone。"""
    try:
        result = run(["gh", "--version"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if match is None:
        return None
    return tuple(int(g) for g in match.groups()) >= GH_ATTACH_MIN_VERSION
