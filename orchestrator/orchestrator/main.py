"""オーケストレータのエントリポイント。

config/projects.yaml を読み込み、5分間隔のポーリングループをバックグラウンド
スレッドで起動しつつ、ダッシュボードから参照可能なHTTP API（GET /api/state）を
メインスレッドで待ち受ける（docs/basic-design.md 2-2）。
"""

from __future__ import annotations

import threading

from orchestrator.config import load_projects
from orchestrator.polling import DEFAULT_INTERVAL_SECONDS, run_polling_loop
from orchestrator.server import StateStore, make_server


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

    polling_thread = threading.Thread(
        target=run_polling_loop,
        kwargs={
            "projects": projects,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "on_update": store.set,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    polling_thread.start()

    server = make_server(store)
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
