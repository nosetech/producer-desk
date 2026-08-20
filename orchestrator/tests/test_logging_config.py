"""orchestrator.logging_config の単体テスト。

レベル制御（ORCHESTRATOR_ENV）・フォーマット統一・日付ローテーション設定
（issue #114）を検証する。
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from orchestrator.logging_config import ENV_VAR, _JstFormatter, configure_logging


def _reset_root_logger() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()


def test_configure_logging_defaults_to_info_level_when_env_unset(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    _reset_root_logger()

    configure_logging(log_path=tmp_path / "orchestrator.log", retention_days=7)

    assert logging.getLogger().level == logging.INFO
    _reset_root_logger()


def test_configure_logging_uses_debug_level_when_development(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_VAR, "development")
    _reset_root_logger()

    configure_logging(log_path=tmp_path / "orchestrator.log", retention_days=7)

    assert logging.getLogger().level == logging.DEBUG
    _reset_root_logger()


def test_configure_logging_attaches_timed_rotating_file_handler_with_retention(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    _reset_root_logger()

    configure_logging(log_path=tmp_path / "orchestrator.log", retention_days=14)

    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    assert handler.when == "MIDNIGHT"
    assert handler.backupCount == 14
    _reset_root_logger()


def test_configure_logging_writes_level_and_message_to_log_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    _reset_root_logger()
    log_path = tmp_path / "orchestrator.log"

    configure_logging(log_path=log_path, retention_days=7)
    logging.getLogger("orchestrator.example").info("hello world")

    content = log_path.read_text(encoding="utf-8")
    assert "[INFO] hello world" in content
    _reset_root_logger()


def test_configure_logging_does_not_stack_handlers_on_repeated_calls(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    _reset_root_logger()

    configure_logging(log_path=tmp_path / "orchestrator.log", retention_days=7)
    first_handler = logging.getLogger().handlers[0]
    configure_logging(log_path=tmp_path / "orchestrator.log", retention_days=7)

    assert len(logging.getLogger().handlers) == 1
    # 前回のハンドラはclear()で参照を外すだけでなくclose()もされ、ファイル
    # ディスクリプタがリークしていないこと（FileHandler.close()はstream属性を
    # Noneにリセットする）。
    assert first_handler.stream is None
    _reset_root_logger()


def test_jst_formatter_formats_time_in_jst_regardless_of_os_timezone() -> None:
    formatter = _JstFormatter("%(asctime)s [%(levelname)s] %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=None,
        exc_info=None,
    )
    # 2026-01-01T00:00:00 UTC は JST で 2026-01-01 09:00:00。
    record.created = 1767225600.0

    formatted_time = formatter.formatTime(record)

    assert formatted_time.startswith("2026-01-01 09:00:00")
