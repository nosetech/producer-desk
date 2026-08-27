"""orchestrator.usage_store の単体テスト。

issue #60: Agent Runner実行結果から得られるモデル別トークン数・コストの
永続化・日次集計・リミット到達検知を検証する。
issue #71: 日次集計の「本日」判定・日付グルーピングがJST（Asia/Tokyo）基準に
なっていることを検証する。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from orchestrator.usage_store import (
    SCHEMA_VERSION,
    DailyModelUsage,
    UsageRecord,
    current_limit_status,
    daily_model_usage,
    parse_limit_reset_text,
    record_usage,
)

FIXED_NOW = lambda: datetime(2026, 8, 9, 4, 0, 0, tzinfo=UTC)  # noqa: E731


def test_parse_limit_reset_text_extracts_reset_clause() -> None:
    message = "You've hit your session limit · resets 1pm (Asia/Tokyo)"

    assert parse_limit_reset_text(message) == "resets 1pm (Asia/Tokyo)"


def test_parse_limit_reset_text_returns_none_when_no_reset_clause() -> None:
    assert parse_limit_reset_text("unexpected error") is None


def test_record_usage_and_daily_model_usage_aggregates_by_day_and_model(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=1000,
                output_tokens=200,
                total_cost_usd=0.5,
            ),
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="deepseek-coder-v2:16b",
                input_tokens=3000,
                output_tokens=800,
                total_cost_usd=0.0,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=2,
                model="claude-sonnet-5",
                input_tokens=500,
                output_tokens=100,
                total_cost_usd=0.25,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    result = daily_model_usage(db_path=db_path, today=FIXED_NOW().date())

    assert result == [
        DailyModelUsage(
            date="2026-08-09",
            model="claude-sonnet-5",
            input_tokens=1500,
            output_tokens=300,
            total_cost_usd=0.75,
        ),
        DailyModelUsage(
            date="2026-08-09",
            model="deepseek-coder-v2:16b",
            input_tokens=3000,
            output_tokens=800,
            total_cost_usd=0.0,
        ),
    ]


def test_daily_model_usage_groups_by_jst_date_not_utc_date(tmp_path: Path) -> None:
    """UTC深夜帯（JST日付変更後・UTC日付変更前）のレコードがJST基準の日付で集計されることを検証する。

    recorded_atは常にUTCで保存されるが、JSTはUTC+9のため、UTC上ではまだ
    前日でもJSTでは既に日付が変わっているケースがある（issue #71）。
    """
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=100,
                output_tokens=10,
                total_cost_usd=0.1,
                # UTC 2026-08-08 20:00 = JST 2026-08-09 05:00（JSTでは既に08-09）
                recorded_at="2026-08-08T20:00:00+00:00",
            ),
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=200,
                output_tokens=20,
                total_cost_usd=0.2,
                # UTC 2026-08-08 14:59 = JST 2026-08-08 23:59（JSTでもまだ08-08）
                recorded_at="2026-08-08T14:59:00+00:00",
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    result = daily_model_usage(db_path=db_path, days=2, today=date(2026, 8, 9))

    assert result == [
        DailyModelUsage(
            date="2026-08-08",
            model="claude-sonnet-5",
            input_tokens=200,
            output_tokens=20,
            total_cost_usd=0.2,
        ),
        DailyModelUsage(
            date="2026-08-09",
            model="claude-sonnet-5",
            input_tokens=100,
            output_tokens=10,
            total_cost_usd=0.1,
        ),
    ]


def test_daily_model_usage_excludes_records_outside_window(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    old_timestamp = "2026-07-01T00:00:00+00:00"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=999,
                output_tokens=999,
                recorded_at=old_timestamp,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    result = daily_model_usage(db_path=db_path, days=7, today=FIXED_NOW().date())

    assert result == []


def test_daily_model_usage_excludes_error_records(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=10,
                output_tokens=10,
                is_error=True,
                api_error_status=429,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    result = daily_model_usage(db_path=db_path, today=FIXED_NOW().date())

    assert result == []


def test_current_limit_status_returns_none_when_no_records(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"

    assert current_limit_status(db_path=db_path) is None


def test_current_limit_status_returns_none_when_latest_record_succeeded(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=10,
                output_tokens=10,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    assert current_limit_status(db_path=db_path) is None


def test_current_limit_status_returns_details_when_latest_record_hit_limit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="claude-sonnet-5",
                input_tokens=10,
                output_tokens=10,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=2,
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                is_error=True,
                api_error_status=429,
                error_message="You've hit your session limit · resets 1pm (Asia/Tokyo)",
                limit_reset_text="resets 1pm (Asia/Tokyo)",
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    status = current_limit_status(db_path=db_path)

    assert status is not None
    assert status.repo == "nosetech/project-a"
    assert status.issue_number == 2
    assert status.reset_at_text == "resets 1pm (Asia/Tokyo)"


def test_current_limit_status_clears_after_subsequent_successful_run(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=2,
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                is_error=True,
                api_error_status=429,
                error_message="resets 1pm (Asia/Tokyo)",
                limit_reset_text="resets 1pm (Asia/Tokyo)",
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )
    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=2,
                model="claude-sonnet-5",
                input_tokens=100,
                output_tokens=50,
            ),
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    assert current_limit_status(db_path=db_path) is None


def test_record_usage_sets_schema_version_on_new_db(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"

    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="m",
                input_tokens=1,
                output_tokens=1,
            )
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_record_usage_upgrades_legacy_db_with_unset_schema_version(tmp_path: Path) -> None:
    """スキーマバージョン管理導入（issue #155）より前に作成されたDBを模す。

    テーブル定義そのものに変更は無いため、user_versionが未設定(0)のまま
    次回アクセス時にSCHEMA_VERSIONへ引き上げられ、以後は通常通り読み書きできる。
    """
    db_path = tmp_path / "usage.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE usage_records ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL, "
            "repo TEXT NOT NULL, issue_number INTEGER NOT NULL, model TEXT NOT NULL, "
            "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, "
            "cache_creation_input_tokens INTEGER NOT NULL, "
            "cache_read_input_tokens INTEGER NOT NULL, "
            "total_cost_usd REAL, is_error INTEGER NOT NULL, api_error_status INTEGER, "
            "error_message TEXT, limit_reset_text TEXT, duration_seconds REAL)"
        )

    record_usage(
        [
            UsageRecord(
                repo="nosetech/project-a",
                issue_number=1,
                model="m",
                input_tokens=1,
                output_tokens=1,
            )
        ],
        db_path=db_path,
        now=FIXED_NOW,
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert daily_model_usage(db_path=db_path, today=date(2026, 8, 9))


def test_record_usage_raises_when_schema_version_is_incompatible(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="スキーマバージョン"):
        record_usage(
            [
                UsageRecord(
                    repo="nosetech/project-a",
                    issue_number=1,
                    model="m",
                    input_tokens=1,
                    output_tokens=1,
                )
            ],
            db_path=db_path,
            now=FIXED_NOW,
        )
