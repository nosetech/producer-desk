"""プロジェクト単位のFIFOディスパッチキュー。

仕様: docs/basic-design.md 2-3「プロジェクト単位のディスパッチキュー」
- プロジェクトごとに実行中フラグ（ロック）を持つ。
- 実行中でなければ即座にディスパッチ、実行中ならキューに追加する。
- 実行中の `claude -p` プロセスが終了次第、キューの先頭のメッセージで次のディスパッチを行う。

実際のAgent Runner起動処理（`claude -p ...`の実行、issue #15の `agent_runner.run_agent_runner`）は
`dispatch_fn` として注入する。結果コメントの投稿先issueを特定できるよう、
issue番号もキューに保持して `dispatch_fn(repo, issue_number, message)` として渡す。
"""

from __future__ import annotations

import collections
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

DispatchFn = Callable[[str, int, str], None]


@dataclass(frozen=True)
class QueueSnapshot:
    """あるリポジトリのキュー状態のスナップショット（issue #233）。

    メッセージ本文は含まない（ダッシュボードの表示に不要なため）。
    同一issueへの指示は重複して積まれうるので、`waiting`には同じ番号が複数並びうる。
    """

    running: int | None = None
    waiting: list[int] = field(default_factory=list)
    # 計画生成ジョブ（issue #287。負のissue番号でキューに積まれる）の実行中・待機数。
    # `running`/`waiting`には実issueのみを含め、計画生成ジョブは含めない。
    planning: bool = False
    plan_waiting: int = 0


class DispatchQueue:
    def __init__(self, dispatch_fn: DispatchFn) -> None:
        self._dispatch_fn = dispatch_fn
        self._lock = threading.Lock()
        self._queues: dict[str, collections.deque[tuple[int, str]]] = collections.defaultdict(
            collections.deque
        )
        self._running: set[str] = set()
        # 各リポジトリで現在ディスパッチ中（`_dispatch_fn`実行中）のissue番号。
        # `is_active()`（issue #50）が「実行中かつどのissueか」まで判定できるように保持する。
        self._current: dict[str, int] = {}

    def enqueue(self, repo: str, issue_number: int, message: str) -> None:
        """メッセージをキューに追加する。実行中でなければワーカーを起動する。"""
        with self._lock:
            self._queues[repo].append((issue_number, message))
            if repo in self._running:
                return
            self._running.add(repo)

        threading.Thread(target=self._run_worker, args=(repo,), daemon=True).start()

    def _run_worker(self, repo: str) -> None:
        while True:
            with self._lock:
                if not self._queues[repo]:
                    self._running.discard(repo)
                    self._current.pop(repo, None)
                    return
                issue_number, message = self._queues[repo].popleft()
                self._current[repo] = issue_number

            self._dispatch_fn(repo, issue_number, message)

    def is_running(self, repo: str) -> bool:
        with self._lock:
            return repo in self._running

    def queue_length(self, repo: str) -> int:
        with self._lock:
            return len(self._queues[repo])

    def snapshot(self, repo: str, *, include_plans: bool = False) -> QueueSnapshot:
        """実行中のissue番号と、待機中のissue番号（FIFO順）をロック配下で取得する（issue #233）。

        既定では計画生成ジョブ（負の番号、issue #287）を`running`/`waiting`から除き、
        件数のみ`planning`/`plan_waiting`で返す。`include_plans=True`のときは
        計画生成ジョブの番号も`waiting`に含める（キュー順位の算出用）。
        """
        with self._lock:
            queue = self._queues.get(repo)
            numbers = [number for number, _ in queue] if queue else []
            current = self._current.get(repo)
            if include_plans:
                return QueueSnapshot(
                    running=current,
                    waiting=numbers,
                    planning=current is not None and current < 0,
                    plan_waiting=sum(1 for n in numbers if n < 0),
                )
            return QueueSnapshot(
                running=current if current is not None and current > 0 else None,
                waiting=[n for n in numbers if n > 0],
                planning=current is not None and current < 0,
                plan_waiting=sum(1 for n in numbers if n < 0),
            )

    def is_current(self, repo: str, issue_number: int) -> bool:
        """指定issueが現在実行中（キュー待ちではなく）かどうかを返す（issue #215）。"""
        with self._lock:
            return self._current.get(repo) == issue_number

    def is_active(self, repo: str, issue_number: int) -> bool:
        """指定issueが現在ディスパッチ中（実行中 or キュー待ち）かどうかを返す（issue #50）。

        `status:in-progress` ラベルが付いているのに実際にはディスパッチキュー上に
        該当issueの実行・待機のいずれも存在しない「孤立したin-progress」を検知する
        `aggregation.aggregate()` から利用される。
        """
        with self._lock:
            if self._current.get(repo) == issue_number:
                return True
            return any(number == issue_number for number, _ in self._queues[repo])
