"""オーケストレータのエントリポイント。

config/projects.yaml を読み込み、5分間隔のポーリングループをバックグラウンド
スレッドで起動しつつ、ダッシュボードとの内部API（docs/basic-design.md 2-2・2-3）を
メインスレッドで待ち受ける。

Agent Runnerの実際の起動処理（`claude -p ...`、issue #15）は未実装のため、
`_placeholder_dispatch` をプレースホルダとして使用する。
"""

from __future__ import annotations

import threading

from orchestrator.comment_watcher import CommentTracker, process_new_comments
from orchestrator.config import load_projects
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.labels import gh_add_label, gh_get_labels, gh_remove_label
from orchestrator.polling import DEFAULT_INTERVAL_SECONDS, run_polling_loop
from orchestrator.server import StateStore, make_server


def _placeholder_dispatch(repo: str, message: str) -> None:
    # TODO(issue #15): claude -p による実際のAgent Runner起動に置き換える。
    print(f"[dispatch] {repo}: {message}")


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
    dispatch_queue = DispatchQueue(dispatch_fn=_placeholder_dispatch)
    comment_tracker = CommentTracker()

    def on_issues_fetched(issues_by_repo: dict) -> None:
        process_new_comments(
            issues_by_repo,
            comment_tracker,
            get_labels=gh_get_labels,
            add_label=gh_add_label,
            remove_label=gh_remove_label,
            dispatch_queue=dispatch_queue,
        )

    polling_thread = threading.Thread(
        target=run_polling_loop,
        kwargs={
            "projects": projects,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "on_update": store.set,
            "on_issues_fetched": on_issues_fetched,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    polling_thread.start()

    server = make_server(store, projects=projects, dispatch_queue=dispatch_queue)
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
