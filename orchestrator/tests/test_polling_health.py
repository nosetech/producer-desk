"""ポーリング健全性の検知・通知のテスト（issue #279）。"""

import threading

from orchestrator.config import Project
from orchestrator.polling import run_polling_loop
from orchestrator.polling_health import (
    MIN_STALL_SECONDS,
    PollingHealth,
    PollingHealthNotifier,
    stall_threshold_seconds,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _notifier(health, posts, *, interval=300.0, threshold=3, url="http://x"):
    return PollingHealthNotifier(
        health,
        interval_seconds=interval,
        failure_threshold=threshold,
        post_webhook=lambda u, p: posts.append(p["text"]),
        get_webhook_url=lambda: url,
    )


def test_no_notification_below_failure_threshold() -> None:
    health, posts = PollingHealth(), []
    n = _notifier(health, posts)
    health.record_failure(RuntimeError("a"))
    health.record_failure(RuntimeError("b"))
    n.check()
    assert posts == []


def test_notifies_once_on_consecutive_failures_then_recovery() -> None:
    health, posts = PollingHealth(), []
    n = _notifier(health, posts)
    for _ in range(3):
        health.record_failure(RuntimeError("boom"))
    n.check()
    health.record_failure(RuntimeError("boom"))
    n.check()
    assert len(posts) == 1
    assert "3回連続" in posts[0] and "boom" in posts[0]

    health.record_success()
    n.check()
    n.check()
    assert len(posts) == 2
    assert "復旧" in posts[1]


def test_detects_stall_without_failures() -> None:
    clock = FakeClock()
    health, posts = PollingHealth(clock=clock), []
    n = _notifier(health, posts)
    health.record_success()
    clock.now += MIN_STALL_SECONDS - 1
    n.check()
    assert posts == []
    clock.now += 2
    n.check()
    n.check()
    assert len(posts) == 1
    assert "停滞" in posts[0]


def test_stall_threshold_scales_with_interval() -> None:
    assert stall_threshold_seconds(60) == MIN_STALL_SECONDS
    assert stall_threshold_seconds(1000) == 3000


def test_no_webhook_url_skips_post_but_does_not_raise() -> None:
    health, posts = PollingHealth(), []
    n = _notifier(health, posts, url=None)
    for _ in range(3):
        health.record_failure(RuntimeError("x"))
    n.check()
    assert posts == []


def test_snapshot_reports_stalled() -> None:
    clock = FakeClock()
    health = PollingHealth(clock=clock)
    health.record_success()
    assert health.snapshot(interval_seconds=300)["stalled"] is False
    clock.now += 3600
    snap = health.snapshot(interval_seconds=300)
    assert snap["stalled"] is True
    assert snap["last_success_at"] is not None


def test_run_polling_loop_records_health() -> None:
    health = PollingHealth()
    stop = threading.Event()
    calls = {"n": 0}

    def list_issues(repo):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("fail")
        stop.set()
        return []

    project = Project(repo="o/r", worktree_path="/tmp/x")
    run_polling_loop(
        [project],
        interval_seconds=0,
        on_update=lambda s: None,
        list_issues=list_issues,
        stop_event=stop,
        health=health,
    )
    snap = health.snapshot(interval_seconds=300)
    assert snap["consecutive_failures"] == 0
    assert snap["last_success_at"] is not None
