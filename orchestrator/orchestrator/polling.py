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


def poll_once(
    projects: list[Project], *, list_issues: ListIssuesFn = list_open_issues
) -> AggregatedState:
    """全プロジェクトを1回ポーリングし、集約結果を返す。"""
    issues_by_repo = {project.repo: list_issues(project.repo) for project in projects}
    return aggregate(issues_by_repo)


def run_polling_loop(
    projects: list[Project],
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    on_update: Callable[[AggregatedState], None],
    list_issues: ListIssuesFn = list_open_issues,
    stop_event: threading.Event | None = None,
) -> None:
    """ポーリングを繰り返し、更新のたびに `on_update` を呼び出す。

    `stop_event` がセットされるまで（未指定なら無期限に）ループする。
    各サイクルの終わりに `interval_seconds` 秒待機する（`stop_event.wait`により
    停止要求があれば即座に抜けられる）。
    """
    stop = stop_event or threading.Event()

    while True:
        state = poll_once(projects, list_issues=list_issues)
        on_update(state)

        if stop.wait(interval_seconds):
            return
