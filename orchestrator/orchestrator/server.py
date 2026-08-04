"""ダッシュボード（Next.js）から参照可能な形でポーリング結果を提供する最小HTTPサーバー。

仕様: docs/basic-design.md 2-2（ダッシュボード表示用の集約データ提供）
ワンタップ承認・却下・自由記述指示（POST側、docs/basic-design.md 2-3）は
issue #14で別途このサーバーに追加する想定のため、ルーティングを拡張しやすい形にする。
"""

from __future__ import annotations

import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orchestrator.aggregation import AggregatedState

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


class StateStore:
    """最新の集約結果をスレッドセーフに保持する。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: AggregatedState | None = None

    def set(self, state: AggregatedState) -> None:
        with self._lock:
            self._state = state

    def get(self) -> AggregatedState | None:
        with self._lock:
            return self._state


def _make_handler(store: StateStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # アクセスログはoff（オーケストレータ本体のログ設計は別issue）

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandlerのインターフェースに合わせる)
            if self.path != "/api/state":
                self.send_response(404)
                self.end_headers()
                return

            state = store.get()
            body = json.dumps(
                dataclasses.asdict(state)
                if state is not None
                else {"decisions": [], "activity": []}
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(
    store: StateStore, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _make_handler(store))
