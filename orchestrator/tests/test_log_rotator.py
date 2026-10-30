"""orchestrator.log_rotator の単体テスト（issue #254）。"""

from __future__ import annotations

import io
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from orchestrator.log_rotator import rotate_stream
from orchestrator.logging_config import JstMidnightRotatingFileHandler
from orchestrator.timezone import JST


def test_lines_are_written_raw(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.log"

    rotate_stream(io.StringIO("first\nTraceback: x\n"), path, 3)

    assert path.read_text(encoding="utf-8") == "first\nTraceback: x\n"


def test_exits_on_stdin_eof(tmp_path: Path) -> None:
    path = tmp_path / "out.log"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.log_rotator",
            "--path",
            str(path),
            "--retention-days",
            "2",
        ],
        input=b"hello\n",
        timeout=30,
        check=True,
    )
    assert result.returncode == 0
    assert path.read_text(encoding="utf-8") == "hello\n"


def test_rollover_creates_dated_backup_and_keeps_writing(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    handler = JstMidnightRotatingFileHandler(path, backup_count=3)
    try:
        handler.emit(_record("old"))
        handler.rolloverAt = int(time.time()) - 1  # 日付境界を越えた状態にする
        expected = datetime.fromtimestamp(handler.rolloverAt - 1, tz=JST).strftime("%Y-%m-%d")
        handler.emit(_record("new"))
    finally:
        handler.close()

    assert (tmp_path / f"a.log.{expected}").read_text(encoding="utf-8") == "old\n"
    assert path.read_text(encoding="utf-8") == "new\n"


def test_backups_beyond_retention_are_deleted(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        (tmp_path / f"a.log.{day}").write_text(day)
    handler = JstMidnightRotatingFileHandler(path, backup_count=2)
    try:
        handler.emit(_record("x"))
        handler.rolloverAt = int(time.time()) - 1
        handler.emit(_record("y"))
    finally:
        handler.close()

    names = sorted(p.name for p in tmp_path.glob("a.log.*"))
    assert len(names) == 2
    assert "a.log.2026-01-01" not in names


def test_rollover_is_jst_midnight_regardless_of_os_tz(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        handler = JstMidnightRotatingFileHandler(tmp_path / "a.log", backup_count=1)
        try:
            # 2026-10-29 10:00 JST の次は 2026-10-30 00:00 JST
            now = int(datetime(2026, 10, 29, 10, 0, tzinfo=JST).timestamp())
            expected = int(datetime(2026, 10, 30, 0, 0, tzinfo=JST).timestamp())
            assert handler.computeRollover(now) == expected
        finally:
            handler.close()
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def _record(msg: str):
    import logging

    r = logging.LogRecord("", logging.INFO, "", 0, msg, None, None)
    return r
