"""orchestrator.dispatch_queue の単体テスト。

docs/basic-design.md 2-3「プロジェクト単位のディスパッチキュー」の仕様
（実行中でなければ即時、実行中ならFIFOキューに追加して完了後に順次処理）を検証する。
"""

from __future__ import annotations

import threading
import time

from orchestrator.dispatch_queue import DispatchQueue


def test_enqueue_dispatches_immediately_when_not_running() -> None:
    calls: list[tuple[str, str]] = []
    done = threading.Event()

    def dispatch_fn(repo: str, message: str) -> None:
        calls.append((repo, message))
        done.set()

    queue = DispatchQueue(dispatch_fn=dispatch_fn)
    queue.enqueue("nosetech/project-a", "hello")

    assert done.wait(timeout=2)
    assert calls == [("nosetech/project-a", "hello")]


def test_enqueue_while_running_is_processed_after_current_dispatch_completes() -> None:
    calls: list[tuple[str, str]] = []
    first_started = threading.Event()
    release_first = threading.Event()
    all_done = threading.Event()

    def dispatch_fn(repo: str, message: str) -> None:
        if message == "first":
            first_started.set()
            release_first.wait(timeout=2)
        calls.append((repo, message))
        if message == "second":
            all_done.set()

    queue = DispatchQueue(dispatch_fn=dispatch_fn)
    queue.enqueue("nosetech/project-a", "first")
    assert first_started.wait(timeout=2)

    # "first"がまだ実行中の間に2件目を投入する -> 実行中なのでキューに積まれる
    queue.enqueue("nosetech/project-a", "second")
    assert queue.queue_length("nosetech/project-a") == 1
    assert queue.is_running("nosetech/project-a") is True

    release_first.set()

    assert all_done.wait(timeout=2)
    assert calls == [("nosetech/project-a", "first"), ("nosetech/project-a", "second")]


def test_different_repos_do_not_block_each_other() -> None:
    calls: list[tuple[str, str]] = []
    lock = threading.Lock()
    a_started = threading.Event()
    release_a = threading.Event()
    b_done = threading.Event()

    def dispatch_fn(repo: str, message: str) -> None:
        if repo == "nosetech/project-a":
            a_started.set()
            release_a.wait(timeout=2)
        with lock:
            calls.append((repo, message))
        if repo == "nosetech/project-b":
            b_done.set()

    queue = DispatchQueue(dispatch_fn=dispatch_fn)
    queue.enqueue("nosetech/project-a", "a-msg")
    assert a_started.wait(timeout=2)

    # project-aが実行中でも、project-bは独立して即時実行される
    queue.enqueue("nosetech/project-b", "b-msg")
    assert b_done.wait(timeout=2)

    release_a.set()
    time.sleep(0.1)

    assert ("nosetech/project-b", "b-msg") in calls
    assert ("nosetech/project-a", "a-msg") in calls


def test_is_running_and_queue_length_reflect_idle_state() -> None:
    def dispatch_fn(repo: str, message: str) -> None:
        pass

    queue = DispatchQueue(dispatch_fn=dispatch_fn)

    assert queue.is_running("nosetech/project-a") is False
    assert queue.queue_length("nosetech/project-a") == 0
