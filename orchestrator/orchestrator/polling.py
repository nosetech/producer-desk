"""複数プロジェクトのGitHub Issuesを定期的にポーリングするループ。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング）、間隔5分）
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from orchestrator.aggregation import AggregatedState, IssueSummary, aggregate
from orchestrator.config import Project
from orchestrator.github_client import list_open_issues

DEFAULT_INTERVAL_SECONDS = 5 * 60

ListIssuesFn = Callable[[str], list[IssueSummary]]
OnIssuesFetchedFn = Callable[[dict[str, list[IssueSummary]]], None]


def poll_once(
    projects: list[Project],
    *,
    list_issues: ListIssuesFn = list_open_issues,
    on_issues_fetched: OnIssuesFetchedFn | None = None,
) -> AggregatedState:
    """全プロジェクトを1回ポーリングし、集約結果を返す。

    `on_issues_fetched` が指定されていれば、集約前の生の取得結果（リポジトリ別issue一覧）
    を渡して呼び出す（直接issueにコメントされた指示の検知など、issue #14の用途）。
    """
    issues_by_repo = {project.repo: list_issues(project.repo) for project in projects}
    if on_issues_fetched is not None:
        on_issues_fetched(issues_by_repo)
    return aggregate(issues_by_repo)


def run_polling_loop(
    projects: list[Project],
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    on_update: Callable[[AggregatedState], None],
    list_issues: ListIssuesFn = list_open_issues,
    on_issues_fetched: OnIssuesFetchedFn | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """ポーリングを繰り返し、更新のたびに `on_update` を呼び出す。

    `stop_event` がセットされるまで（未指定なら無期限に）ループする。
    各サイクルの終わりに `interval_seconds` 秒待機する（`stop_event.wait`により
    停止要求があれば即座に抜けられる）。
    """
    stop = stop_event or threading.Event()

    while True:
        state = poll_once(projects, list_issues=list_issues, on_issues_fetched=on_issues_fetched)
        on_update(state)

        if stop.wait(interval_seconds):
            return
