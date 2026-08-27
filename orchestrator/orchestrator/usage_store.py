"""Agent Runner実行結果の利用量（トークン数・コスト・リミット到達）の永続化・集計。

仕様: docs/basic-design.md 2-2「利用量・リミットモニター」、issue #60

正確な利用率(%)（セッション5時間枠・週間上限に対する消費率）はAgent Runnerの
実行結果（`claude -p ... --output-format stream-json --verbose`のNDJSON出力から
取り出した最後の`"type":"result"`イベント）からは取得できないため、実行の
たびに得られる `usage.*` / `modelUsage.*` / `total_cost_usd` を`config/usage.db`
（.gitignore対象、コミットしない）にSQLiteで記録し、「日単位の使用量」として
モデル別に集計・表示する方式に転換した。

`duration_seconds` はOllama REST APIの`total_duration`相当（秒）。MCP
`ollama-client`経由の呼び出しではメトリクスが取得できないため、`orchestrator/
orchestrator/ollama_bench.py`（`ollama-bench` CLI、Ollama REST APIを直接呼び
出す。手動ベンチマークとAgent Runner本番経路のローカルLLM生成呼び出しの両方
から使われる。issue #107）からのみ値が入る。Claude Code実行分の記録では常に
`None`になる。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from orchestrator.config import REPO_ROOT
from orchestrator.timezone import JST as _JST

DEFAULT_USAGE_DB_PATH = REPO_ROOT / "config" / "usage.db"

# 利用量の日次集計はJST（Asia/Tokyo）基準で行う。record_usage()が保存する
# recorded_at自体はUTCのまま（絶対時刻として一意）だが、daily_model_usage()の
# 「本日」判定・日付グルーピングはJSTへ変換してから行う（issue #71。JST定義
# 自体はログ出力設計（logging_config.py・agent_runner.py）と共有するため
# orchestrator/timezone.py に切り出した。issue #114）。

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

# config/usage.dbのスキーマバージョン（SQLiteの`PRAGMA user_version`で管理）。
# 将来テーブル定義を変更する場合はこの値をインクリメントし、_connect()に
# 旧バージョンからの変換ロジックを追加する。配布パッケージのバージョンアップ時に
# 状態ファイルを引き継ぐ dist/scripts/migrate.sh は、コピー可否の判定にこの値と
# 同じ値（EXPECTED_USAGE_DB_SCHEMA_VERSION）を独立に保持しているため、この値を
# 変更する際は同スクリプトも合わせて更新すること（issue #155）。
SCHEMA_VERSION = 1


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

    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version == 0:
        # 新規作成時、またはスキーマバージョン管理導入（issue #155）より前に
        # 作成された既存DB。後者はテーブル定義に変更が無いため、そのまま
        # SCHEMA_VERSIONを書き込んで問題ない。
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif current_version != SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} のスキーマバージョン({current_version})が、現在のコードが"
            f"期待するバージョン({SCHEMA_VERSION})と一致しません。対応するバージョン"
            "の dist/scripts/migrate.sh を使うか、手動でスキーマを移行してください。"
        )
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
