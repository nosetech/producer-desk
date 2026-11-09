"""ポーリングループ自身の健全性（連続失敗・最終成功時刻）の追跡と通知（issue #279）。

`state.last_polled_at` は `server._refresh_store`（ダッシュボード操作経由）でも更新されるため、
ポーリングスレッドが止まっていても停止に気付けない。ここではポーリングループ自身の
成功・失敗だけを記録し、連続失敗・停滞（一定時間成功がない）を検知してSlack通知する。

通知は障害ごとに1回だけ（同一障害での連続通知を避ける）、復旧時にも1回通知する。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from orchestrator.slack_notifier import (
    GetWebhookUrlFn,
    PostWebhookFn,
    _default_get_webhook_url,
    post_slack_webhook,
)

logger = logging.getLogger(__name__)

# 連続失敗がこの回数に達したら通知する（5分間隔なら約15分）
DEFAULT_FAILURE_THRESHOLD = 3
# ポーリング間隔のこの倍数以上成功がなければ停滞とみなす
STALL_INTERVAL_MULTIPLIER = 3
# 停滞判定の下限（短いポーリング間隔でも誤検知しないため）
MIN_STALL_SECONDS = 15 * 60


def stall_threshold_seconds(interval_seconds: float) -> float:
    return max(interval_seconds * STALL_INTERVAL_MULTIPLIER, MIN_STALL_SECONDS)


class PollingHealth:
    """ポーリングループ自身の最終成功時刻・連続失敗回数を保持する（スレッドセーフ）。"""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at = clock()
        self._last_success_monotonic: float | None = None
        self._last_success_at: str | None = None
        self._consecutive_failures = 0
        self._last_error: str | None = None

    def record_success(self) -> None:
        with self._lock:
            self._last_success_monotonic = self._clock()
            self._last_success_at = datetime.now(UTC).isoformat(timespec="seconds")
            self._consecutive_failures = 0
            self._last_error = None

    def record_failure(self, error: BaseException) -> int:
        """失敗を記録し、現在の連続失敗回数を返す。"""
        with self._lock:
            self._consecutive_failures += 1
            self._last_error = f"{type(error).__name__}: {error}"
            return self._consecutive_failures

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def seconds_since_last_success(self) -> float:
        """最終成功からの経過秒数。未成功なら起動からの経過秒数。"""
        with self._lock:
            base = (
                self._last_success_monotonic
                if self._last_success_monotonic is not None
                else self._started_at
            )
            return self._clock() - base

    def snapshot(self, *, interval_seconds: float) -> dict:
        with self._lock:
            base = (
                self._last_success_monotonic
                if self._last_success_monotonic is not None
                else self._started_at
            )
            elapsed = self._clock() - base
            return {
                "last_success_at": self._last_success_at,
                "consecutive_failures": self._consecutive_failures,
                "last_error": self._last_error,
                "seconds_since_last_success": round(elapsed, 1),
                "stalled": elapsed >= stall_threshold_seconds(interval_seconds),
            }


class PollingHealthNotifier:
    """連続失敗・停滞を検知してSlack通知する。障害ごとに1回のみ、復旧時にも1回通知する。"""

    def __init__(
        self,
        health: PollingHealth,
        *,
        interval_seconds: float,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        post_webhook: PostWebhookFn = post_slack_webhook,
        get_webhook_url: GetWebhookUrlFn = _default_get_webhook_url,
    ) -> None:
        self._health = health
        self._stall_seconds = stall_threshold_seconds(interval_seconds)
        self._failure_threshold = failure_threshold
        self._post_webhook = post_webhook
        self._get_webhook_url = get_webhook_url
        self._alerting = False

    def _post(self, text: str) -> None:
        url = self._get_webhook_url()
        if not url:
            return
        try:
            self._post_webhook(url, {"text": text})
        except Exception:
            logger.exception("ポーリング異常のSlack通知に失敗しました")

    def check(self) -> None:
        """状態を評価し、必要なら通知する（ポーリング周期ごと・監視スレッドから呼ぶ）。"""
        failures = self._health.consecutive_failures
        elapsed = self._health.seconds_since_last_success()
        unhealthy = failures >= self._failure_threshold or elapsed >= self._stall_seconds

        if unhealthy and not self._alerting:
            self._alerting = True
            if failures >= self._failure_threshold:
                reason = f"ポーリングが{failures}回連続で失敗しています"
            else:
                reason = f"ポーリングが{int(elapsed // 60)}分以上成功していません（停滞の疑い）"
            snap = self._health.snapshot(interval_seconds=0)
            self._post(
                f":warning: {reason}\n*最終エラー*: {snap['last_error'] or 'なし'}\n"
                f"*最終成功*: {snap['last_success_at'] or '起動後なし'}"
            )
        elif not unhealthy and self._alerting:
            self._alerting = False
            self._post(":white_check_mark: ポーリングが復旧しました")


def run_health_watchdog(
    notifier: PollingHealthNotifier,
    stop_event: threading.Event,
    *,
    check_interval_seconds: float = 60,
) -> None:
    """ポーリングスレッドとは別スレッドで停滞を監視する（ポーリング自体が止まっても検知するため）。"""
    while not stop_event.wait(check_interval_seconds):
        try:
            notifier.check()
        except Exception:
            logger.exception("ポーリング健全性の監視でエラーが発生しました")
