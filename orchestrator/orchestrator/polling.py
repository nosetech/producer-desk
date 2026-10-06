"""複数プロジェクトのGitHub Issuesを定期的にポーリングするループ。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング）、間隔5分）
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from orchestrator.aggregation import AggregatedState, IsDispatchActiveFn, IssueSummary, aggregate
from orchestrator.config import Project
from orchestrator.github_client import list_issues as gh_list_issues
from orchestrator.github_client import resolve_pr_number as gh_resolve_pr_number
from orchestrator.labels import STATUS_IN_REVIEW

DEFAULT_INTERVAL_SECONDS = 5 * 60

ListIssuesFn = Callable[[str], list[IssueSummary]]
ResolvePrNumberFn = Callable[[str, int], int | None]
OnIssuesFetchedFn = Callable[[dict[str, list[IssueSummary]]], None]


def _resolve_review_pr_numbers(
    issues_by_repo: dict[str, list[IssueSummary]], resolve_pr_number: ResolvePrNumberFn
) -> None:
    """`status:in-review` のissueについてのみ紐づくPR番号を解決する（issue #58）。

    全issueに対して毎回Timeline APIを叩くとポーリング負荷が増えるため、対象を絞る。
    """
    for issues in issues_by_repo.values():
        for issue in issues:
            if STATUS_IN_REVIEW in issue.labels:
                issue.pr_number = resolve_pr_number(issue.repo, issue.number)


def now_iso() -> str:
    """現在時刻をISO 8601（UTC、秒精度）で返す。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


def fetch_project_issues(
    project: Project,
    *,
    list_issues: ListIssuesFn = gh_list_issues,
    resolve_pr_number: ResolvePrNumberFn = gh_resolve_pr_number,
) -> list[IssueSummary]:
    """1プロジェクト分のissueを取得し、`status:in-review` のPR番号を解決して返す（issue #197）。

    `poll_once`（全プロジェクト）と、プロジェクト単位の再取得エンドポイントの双方から
    使う共通の取得ロジック。
    """
    issues = list_issues(project.repo)
    _resolve_review_pr_numbers({project.repo: issues}, resolve_pr_number)
    return issues


def poll_once(
    projects: list[Project],
    *,
    list_issues: ListIssuesFn = gh_list_issues,
    resolve_pr_number: ResolvePrNumberFn = gh_resolve_pr_number,
    on_issues_fetched: OnIssuesFetchedFn | None = None,
    is_dispatch_active: IsDispatchActiveFn | None = None,
) -> AggregatedState:
    """全プロジェクトを1回ポーリングし、集約結果を返す。

    `on_issues_fetched` が指定されていれば、集約前の生の取得結果（リポジトリ別issue一覧）
    を渡して呼び出す（直接issueにコメントされた指示の検知など、issue #14の用途）。
    `is_dispatch_active`（`DispatchQueue.is_active`、issue #50）を指定すると、
    `aggregate()` が孤立したin-progressissueを検知する。`on_issues_fetched` によって
    このポーリング内でディスパッチが行われた場合も、その結果は集約前に反映される
    （enqueue()はディスパッチスレッド起動前に同期的にキューへ積むため）。

    `on_issues_fetched` はコメント指示検知・クローズ検知経由でオーケストレータ自身が
    `labels.transition_label()` を呼び、GitHub側のラベルを書き換えることがある
    （issue #97）。この変更は呼び出し前に取得済みの `issues_by_repo` には反映されない
    ため、`on_issues_fetched` 呼び出し後に `issues_by_repo` を取得し直してから
    `aggregate()` に渡し、同一ポーリングサイクル内のラベル遷移をプロジェクト状況に
    即時反映させる。`on_issues_fetched` が `None`（`server._refresh_store` からの
    呼び出し等、オーケストレータ自身によるラベル遷移が起きない経路）の場合は
    再取得せず、無駄なGitHub API呼び出しを避ける。
    """

    def fetch_all() -> tuple[dict[str, list[IssueSummary]], dict[str, str]]:
        issues_by_repo: dict[str, list[IssueSummary]] = {}
        fetched_at_by_repo: dict[str, str] = {}
        for project in projects:
            issues_by_repo[project.repo] = fetch_project_issues(
                project, list_issues=list_issues, resolve_pr_number=resolve_pr_number
            )
            fetched_at_by_repo[project.repo] = now_iso()
        return issues_by_repo, fetched_at_by_repo

    issues_by_repo, fetched_at_by_repo = fetch_all()
    if on_issues_fetched is not None:
        on_issues_fetched(issues_by_repo)
        issues_by_repo, fetched_at_by_repo = fetch_all()
    return aggregate(
        issues_by_repo,
        is_dispatch_active=is_dispatch_active,
        fetched_at_by_repo=fetched_at_by_repo,
        last_polled_at=now_iso(),
    )


def run_polling_loop(
    projects: list[Project],
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    on_update: Callable[[AggregatedState], None],
    list_issues: ListIssuesFn = gh_list_issues,
    resolve_pr_number: ResolvePrNumberFn = gh_resolve_pr_number,
    on_issues_fetched: OnIssuesFetchedFn | None = None,
    is_dispatch_active: IsDispatchActiveFn | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """ポーリングを繰り返し、更新のたびに `on_update` を呼び出す。

    `stop_event` がセットされるまで（未指定なら無期限に）ループする。
    各サイクルの終わりに `interval_seconds` 秒待機する（`stop_event.wait`により
    停止要求があれば即座に抜けられる）。
    """
    stop = stop_event or threading.Event()

    while True:
        state = poll_once(
            projects,
            list_issues=list_issues,
            resolve_pr_number=resolve_pr_number,
            on_issues_fetched=on_issues_fetched,
            is_dispatch_active=is_dispatch_active,
        )
        on_update(state)

        if stop.wait(interval_seconds):
            return
