"""オーケストレータのエントリポイント。

config/projects.yaml を読み込み、5分間隔のポーリングループをバックグラウンド
スレッドで起動しつつ、ダッシュボードとの内部API（docs/basic-design.md 2-2・2-3）を
メインスレッドで待ち受ける。ディスパッチキューに投入された指示は、Agent Runner
（Claude Code CLIのワンショット実行、docs/basic-design.md 3章）に渡される。
"""

from __future__ import annotations

import logging
import os
import threading

from orchestrator.agent_runner import run_agent_runner
from orchestrator.aggregation import AggregatedState
from orchestrator.ci_watcher import CiWaitTracker, process_ci_waiting_issues
from orchestrator.close_watcher import close_finished_issues
from orchestrator.comment_watcher import CommentTracker, process_new_comments
from orchestrator.config import Project, load_log_retention_days, load_projects
from orchestrator.dispatch_queue import DispatchFn, DispatchQueue
from orchestrator.github_client import get_pr_status_check_rollup as gh_get_pr_status_check_rollup
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.labels import gh_add_label, gh_get_labels, gh_remove_label
from orchestrator.logging_config import configure_logging
from orchestrator.polling import DEFAULT_INTERVAL_SECONDS, run_polling_loop
from orchestrator.server import DEFAULT_PORT, StateStore, make_server
from orchestrator.slack_notifier import DecisionNotifier, ReviewNotifier

logger = logging.getLogger(__name__)

# 環境変数 ORCHESTRATOR_PORT でbindポートを上書きできる。既に本番用インスタンスが
# 稼働中の状態でAgent Runner自身が動作確認のために別インスタンスを起動する際、
# ポート衝突を避けるために使う（CLAUDE.md「開発ワークフロー」参照）。
PORT_ENV = "ORCHESTRATOR_PORT"


def _make_dispatch_fn(projects: list[Project], log_retention_days: int) -> DispatchFn:
    projects_by_repo = {project.repo: project for project in projects}

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        run_agent_runner(
            projects_by_repo[repo],
            issue_number,
            message,
            log_retention_days=log_retention_days,
        )

    return dispatch_fn


def main() -> None:
    log_retention_days = load_log_retention_days()
    configure_logging(retention_days=log_retention_days)

    projects = load_projects()

    if not projects:
        logger.error("config/projects.yaml にプロジェクトが登録されていません。")
        return

    logger.info("%d件のプロジェクトを読み込みました:", len(projects))
    for project in projects:
        logger.info("  - %s (%s)", project.repo, project.worktree_path)

    store = StateStore()
    stop_event = threading.Event()
    dispatch_queue = DispatchQueue(dispatch_fn=_make_dispatch_fn(projects, log_retention_days))
    comment_tracker = CommentTracker()
    ci_wait_tracker = CiWaitTracker()
    decision_notifier = DecisionNotifier()
    review_notifier = ReviewNotifier()

    def on_issues_fetched(issues_by_repo: dict) -> None:
        close_finished_issues(
            issues_by_repo,
            get_labels=gh_get_labels,
            add_label=gh_add_label,
            remove_label=gh_remove_label,
        )
        process_new_comments(
            issues_by_repo,
            comment_tracker,
            get_labels=gh_get_labels,
            add_label=gh_add_label,
            remove_label=gh_remove_label,
            dispatch_queue=dispatch_queue,
        )
        # issue #173: CI完了待機のため意図的にstatus:in-progressのまま終了した
        # issueについて、対象PRのCI完了を検知したらAgent Runnerを自動再開する
        # （検知できずタイムアウトした場合はneeds-human-decisionへフェイルセーフ）。
        process_ci_waiting_issues(
            issues_by_repo,
            ci_wait_tracker,
            get_labels=gh_get_labels,
            add_label=gh_add_label,
            remove_label=gh_remove_label,
            get_pr_status_check_rollup=gh_get_pr_status_check_rollup,
            dispatch_queue=dispatch_queue,
            post_comment=gh_post_comment,
        )

    def on_update(state: AggregatedState) -> None:
        store.set(state)
        decision_notifier.notify_new_decisions(state)
        review_notifier.notify_new_reviews(state)

    polling_thread = threading.Thread(
        target=run_polling_loop,
        kwargs={
            "projects": projects,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "on_update": on_update,
            "on_issues_fetched": on_issues_fetched,
            "is_dispatch_active": dispatch_queue.is_active,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    polling_thread.start()

    port = int(os.environ.get(PORT_ENV, DEFAULT_PORT))
    server = make_server(store, projects=projects, dispatch_queue=dispatch_queue, port=port)
    logger.info(
        "APIサーバーを起動しました: http://%s:%s/api/state",
        server.server_address[0],
        server.server_address[1],
    )
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.shutdown()


if __name__ == "__main__":
    main()
