"""利用リミット待ち（issue #331）の機械可読マーカーの組み立て・抽出。

Claude Code（サブスクリプション）の利用リミット（429）でAgent Runnerが異常終了し、
解除予定時刻を絶対時刻に変換できた場合、`agent_runner._build_failure_comment`は
失敗コメントに`LIMIT_WAIT_MARKER_PREFIX`のマーカー（解除予定時刻・連続の自動再開回数）を
埋め込む。`orchestrator.limit_watcher`はポーリングのたびに、最新コメントがこのマーカー付き
のissueを探し、解除予定時刻を過ぎていれば同じセッションを`--resume`で再開する。

待機状態はコメントから毎回導けるため、追加の永続化ファイルは持たない（オーケストレータを
再起動しても待機は失われない）。マーカーの後に人間のコメント（返信・別モデル指定）や
取り消しコメントが付けば最新コメントではなくなり、自動再開の対象から外れる。

本モジュールは他のorchestratorモジュールに依存しない（`aggregation`・`agent_runner`の
双方から循環なしにimportするため）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

LIMIT_WAIT_MARKER_PREFIX = "<!-- producer-desk:limit-wait"
# 自動再開時にAgent Runnerへ渡すメッセージに付ける、連続の自動再開回数のマーカー。
# 再開後にまた429になった場合、`agent_runner`はこの回数を引き継いで次のマーカーを付ける。
LIMIT_RESUME_MARKER_PREFIX = "<!-- producer-desk:limit-resume"
# 自動再開の取り消しコメント（`POST .../limit-wait/cancel`）に付けるマーカー。
LIMIT_WAIT_CANCEL_MARKER = "<!-- producer-desk:limit-wait-cancel -->"

_LIMIT_WAIT_PATTERN = re.compile(
    re.escape(LIMIT_WAIT_MARKER_PREFIX) + r"\s*(\{.*?\})\s*-->", re.DOTALL
)
_LIMIT_RESUME_PATTERN = re.compile(
    re.escape(LIMIT_RESUME_MARKER_PREFIX) + r"\s*(\{.*?\})\s*-->", re.DOTALL
)

# 自動再開時のメッセージ（`--resume`したセッションへの指示）。
LIMIT_RESUMED_MESSAGE = (
    "利用リミットの解除予定時刻を過ぎたため、オーケストレータが自動で再開しました。"
    "中断した作業の続きを進めてください。"
)


@dataclass(frozen=True)
class LimitWait:
    """利用リミット待ちマーカーの内容。"""

    reset_at: datetime
    # 連続の自動再開のうち何回目の待機か（1始まり）。
    attempt: int


def _load_json(pattern: re.Pattern[str], text: str | None) -> dict | None:
    if not text:
        return None
    match = pattern.search(text)
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("利用リミット待ちのマーカーをJSONとしてパースできませんでした。")
        return None
    return data if isinstance(data, dict) else None


def build_limit_wait_marker(reset_at: datetime, attempt: int) -> str:
    payload = json.dumps({"reset_at": reset_at.isoformat(), "attempt": attempt})
    return f"{LIMIT_WAIT_MARKER_PREFIX}\n{payload}\n-->"


def extract_limit_wait_marker(text: str | None) -> LimitWait | None:
    """本文から利用リミット待ちマーカーを抽出する。不正・タイムゾーン無しの時刻はNone。"""
    data = _load_json(_LIMIT_WAIT_PATTERN, text)
    if data is None:
        return None
    raw_reset_at = data.get("reset_at")
    if not isinstance(raw_reset_at, str):
        return None
    try:
        reset_at = datetime.fromisoformat(raw_reset_at)
    except ValueError:
        return None
    if reset_at.tzinfo is None:
        return None
    attempt = data.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        attempt = 1
    return LimitWait(reset_at=reset_at, attempt=attempt)


def build_limit_resume_message(attempt: int) -> str:
    payload = json.dumps({"attempt": attempt})
    return f"{LIMIT_RESUMED_MESSAGE}\n\n{LIMIT_RESUME_MARKER_PREFIX}\n{payload}\n-->"


def extract_limit_resume_attempt(message: str | None) -> int:
    """自動再開メッセージに付いた連続の自動再開回数。自動再開でなければ0。"""
    data = _load_json(_LIMIT_RESUME_PATTERN, message)
    if data is None:
        return 0
    attempt = data.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        return 0
    return attempt
