"""Agent Runner実行結果の利用量（トークン数・コスト・リミット到達）の永続化・集計。

仕様: docs/basic-design.md 2-2「利用量・リミットモニター」、issue #60

正確な利用率(%)（セッション5時間枠・週間上限に対する消費率）はAgent Runnerの
実行結果（`claude -p ... --output-format json`）からは取得できないため、実行の
たびに得られる `usage.*` / `modelUsage.*` / `total_cost_usd` を`config/usage.db`
（.gitignore対象、コミットしない）にSQLiteで記録し、「日単位の使用量」として
モデル別に集計・表示する方式に転換した。

`duration_seconds` はOllama REST APIの`total_duration`相当（秒）。Agent Runner
本番経路（MCP `ollama-client`経由）では取得できず、`orchestrator/orchestrator/
ollama_bench.py`（手動ベンチマークツール、Ollama REST APIを直接呼び出す）から
のみ値が入る。Claude Code実行分の記録では常に`None`になる。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from orchestrator.config import REPO_ROOT

DEFAULT_USAGE_DB_PATH = REPO_ROOT / "config" / "usage.db"

# 利用量の日次集計はJST（Asia/Tokyo）基準で行う。record_usage()が保存する
# recorded_at自体はUTCのまま（絶対時刻として一意）だが、daily_model_usage()の
# 「本日」判定・日付グルーピングはJSTへ変換してから行う（issue #71）。
_JST = ZoneInfo("Asia/Tokyo")

# リミット到達時、`result`の自由文（例: "You've hit your session limit ·
# resets 1pm (Asia/Tokyo)"）から解除予定時刻の記述部分を抜き出す。
# 構造化フィールドではないため、パース失敗時は生の文字列をそのまま保存する
# フォールバックを`parse_limit_reset_text`呼び出し側で行う。
_LIMIT_RESET_PATTERN = re.compile(r"resets?\s+.+$", re.IGNORECASE)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    repo TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_input_tokens INTEGER NOT NULL,
    cache_read_input_tokens INTEGER NOT NULL,
    total_cost_usd REAL,
    is_error INTEGER NOT NULL,
    api_error_status INTEGER,
    error_message TEXT,
    limit_reset_text TEXT,
    duration_seconds REAL
)
"""


@dataclass
class UsageRecord:
    repo: str
    issue_number: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_cost_usd: float | None = None
    is_error: bool = False
    api_error_status: int | None = None
    error_message: str | None = None
    limit_reset_text: str | None = None
    duration_seconds: float | None = None  # Ollama REST APIの`total_duration`相当（秒）
    recorded_at: str | None = None  # 未指定時はrecord_usage呼び出し時刻を使う


@dataclass
class DailyModelUsage:
    date: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float


@dataclass
class LimitStatus:
    repo: str
    issue_number: int
    recorded_at: str
    api_error_status: int | None
    error_message: str
    reset_at_text: str | None


RecordUsageFn = Callable[..., None]


def parse_limit_reset_text(message: str) -> str | None:
    match = _LIMIT_RESET_PATTERN.search(message)
    return match.group(0).strip() if match else None


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def record_usage(
    records: Iterable[UsageRecord],
    *,
    db_path: Path = DEFAULT_USAGE_DB_PATH,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """実行結果から得られたモデル別利用量レコードを追記する。"""
    records = list(records)
    if not records:
        return

    timestamp = now().isoformat()
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO usage_records ("
            "recorded_at, repo, issue_number, model, input_tokens, output_tokens, "
            "cache_creation_input_tokens, cache_read_input_tokens, total_cost_usd, "
            "is_error, api_error_status, error_message, limit_reset_text, duration_seconds"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    record.recorded_at or timestamp,
                    record.repo,
                    record.issue_number,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.cache_creation_input_tokens,
                    record.cache_read_input_tokens,
                    record.total_cost_usd,
                    int(record.is_error),
                    record.api_error_status,
                    record.error_message,
                    record.limit_reset_text,
                    record.duration_seconds,
                )
                for record in records
            ],
        )


def daily_model_usage(
    *,
    db_path: Path = DEFAULT_USAGE_DB_PATH,
    days: int = 7,
    today: date | None = None,
) -> list[DailyModelUsage]:
    """過去`days`日分（当日含む）の日次・モデル別利用量集計を返す。

    リミット到達等のエラー実行（トークン消費が実質無い、または不正確な）は
    集計対象から除外する。
    """
    today = today or datetime.now(_JST).date()
    since = (today - timedelta(days=days - 1)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT substr(datetime(recorded_at, '+9 hours'), 1, 10) AS day, model, "
            "SUM(input_tokens), SUM(output_tokens), SUM(COALESCE(total_cost_usd, 0)) "
            "FROM usage_records "
            "WHERE substr(datetime(recorded_at, '+9 hours'), 1, 10) >= ? AND is_error = 0 "
            "GROUP BY day, model "
            "ORDER BY day ASC, model ASC",
            (since,),
        ).fetchall()
    return [
        DailyModelUsage(
            date=row[0],
            model=row[1],
            input_tokens=row[2],
            output_tokens=row[3],
            total_cost_usd=row[4],
        )
        for row in rows
    ]


def current_limit_status(*, db_path: Path = DEFAULT_USAGE_DB_PATH) -> LimitStatus | None:
    """直近の実行がリミット到達（429）で終わっている場合、その内容を返す。

    Anthropicアカウント側のセッション5時間枠・週間上限はプロジェクト横断の
    単一契約に紐づくため、リポジトリを問わず最新の1件のみを見る。次の実行が
    成功すればそれが最新レコードになるため、追加の状態管理をせずに解除を
    検知できる。
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT repo, issue_number, recorded_at, is_error, api_error_status, "
            "error_message, limit_reset_text "
            "FROM usage_records ORDER BY recorded_at DESC, id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None

    repo, issue_number, recorded_at, is_error, api_error_status, error_message, limit_reset_text = (
        row
    )
    if not is_error or api_error_status != 429:
        return None

    return LimitStatus(
        repo=repo,
        issue_number=issue_number,
        recorded_at=recorded_at,
        api_error_status=api_error_status,
        error_message=error_message or "",
        reset_at_text=limit_reset_text,
    )
