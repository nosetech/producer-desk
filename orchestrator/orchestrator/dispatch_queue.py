"""プロジェクト単位のFIFOディスパッチキュー。

仕様: docs/basic-design.md 2-3「プロジェクト単位のディスパッチキュー」
- プロジェクトごとに実行中フラグ（ロック）を持つ。
- 実行中でなければ即座にディスパッチ、実行中ならキューに追加する。
- 実行中の `claude -p` プロセスが終了次第、キューの先頭のメッセージで次のディスパッチを行う。

実際のAgent Runner起動処理（`claude -p ...`の実行、issue #15）は `dispatch_fn` として
注入する。本issueの時点ではプレースホルダを想定している。
"""

from __future__ import annotations

import collections
import threading
from collections.abc import Callable

DispatchFn = Callable[[str, str], None]


class DispatchQueue:
    def __init__(self, dispatch_fn: DispatchFn) -> None:
        self._dispatch_fn = dispatch_fn
        self._lock = threading.Lock()
        self._queues: dict[str, collections.deque[str]] = collections.defaultdict(collections.deque)
        self._running: set[str] = set()

    def enqueue(self, repo: str, message: str) -> None:
        """メッセージをキューに追加する。実行中でなければワーカーを起動する。"""
        with self._lock:
            self._queues[repo].append(message)
            if repo in self._running:
                return
            self._running.add(repo)

        threading.Thread(target=self._run_worker, args=(repo,), daemon=True).start()

    def _run_worker(self, repo: str) -> None:
        while True:
            with self._lock:
                if not self._queues[repo]:
                    self._running.discard(repo)
                    return
                message = self._queues[repo].popleft()

            self._dispatch_fn(repo, message)

    def is_running(self, repo: str) -> bool:
        with self._lock:
            return repo in self._running

    def queue_length(self, repo: str) -> int:
        with self._lock:
            return len(self._queues[repo])
