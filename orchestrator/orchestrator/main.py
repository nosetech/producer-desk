"""オーケストレータのエントリポイント。

config/projects.yaml を読み込み、5分間隔のポーリングループをバックグラウンド
スレッドで起動しつつ、ダッシュボードとの内部API（docs/basic-design.md 2-2・2-3）を
メインスレッドで待ち受ける。ディスパッチキューに投入された指示は、Agent Runner
（Claude Code CLIのワンショット実行、docs/basic-design.md 3章）に渡される。
"""

from __future__ import annotations

import os
import threading

from orchestrator.agent_runner import run_agent_runner
from orchestrator.aggregation import AggregatedState
from orchestrator.close_watcher import close_finished_issues
from orchestrator.comment_watcher import CommentTracker, process_new_comments
from orchestrator.config import Project, load_projects
from orchestrator.dispatch_queue import DispatchFn, DispatchQueue
from orchestrator.labels import gh_add_label, gh_get_labels, gh_remove_label
from orchestrator.polling import DEFAULT_INTERVAL_SECONDS, run_polling_loop
from orchestrator.server import DEFAULT_PORT, StateStore, make_server
from orchestrator.slack_notifier import DecisionNotifier, ReviewNotifier

# 環境変数 ORCHESTRATOR_PORT でbindポートを上書きできる。既に本番用インスタンスが
# 稼働中の状態でAgent Runner自身が動作確認のために別インスタンスを起動する際、
# ポート衝突を避けるために使う（CLAUDE.md「開発ワークフロー」参照）。
PORT_ENV = "ORCHESTRATOR_PORT"


def _make_dispatch_fn(projects: list[Project]) -> DispatchFn:
    projects_by_repo = {project.repo: project for project in projects}

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        run_agent_runner(projects_by_repo[repo], issue_number, message)

    return dispatch_fn


def main() -> None:
    projects = load_projects()

    if not projects:
        print("config/projects.yaml にプロジェクトが登録されていません。")
        return

    print(f"{len(projects)}件のプロジェクトを読み込みました:")
    for project in projects:
        print(f"  - {project.repo} ({project.worktree_path})")

    store = StateStore()
    stop_event = threading.Event()
    dispatch_queue = DispatchQueue(dispatch_fn=_make_dispatch_fn(projects))
    comment_tracker = CommentTracker()
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
    print(
        f"APIサーバーを起動しました: http://{server.server_address[0]}:{server.server_address[1]}/api/state"
    )
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.shutdown()


if __name__ == "__main__":
    main()
