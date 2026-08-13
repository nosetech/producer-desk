"""複数プロジェクトのGitHub Issuesを定期的にポーリングするループ。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング）、間隔5分）
"""

from __future__ import annotations

import threading
from collections.abc import Callable

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
    """
    issues_by_repo = {project.repo: list_issues(project.repo) for project in projects}
    _resolve_review_pr_numbers(issues_by_repo, resolve_pr_number)
    if on_issues_fetched is not None:
        on_issues_fetched(issues_by_repo)
    return aggregate(issues_by_repo, is_dispatch_active=is_dispatch_active)


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
