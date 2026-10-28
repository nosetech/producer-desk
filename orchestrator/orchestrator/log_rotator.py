"""標準入力を読み、日次ローテーション付きでファイルへ書き出す小さなローテータ。

仕様: issue #254。`bin/start.sh`は本体（orchestrator・dashboard）のstdout/stderrを
このスクリプトへパイプする。シェルの`>>`リダイレクトだと、ローテーションで
renameされた後もシェルのfdが旧inodeを指し続けるため（issue #114）、書き込み側
（このプロセス）が自分でファイルを開き直す方式にしている。

使い方: `python -m orchestrator.log_rotator --path <file> [--retention-days <n>]`
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from orchestrator.config import DEFAULT_LOG_RETENTION_DAYS, load_log_retention_days
from orchestrator.logging_config import JstMidnightRotatingFileHandler


def rotate_stream(lines: Iterable[str], path: Path, retention_days: int) -> None:
    """`lines`をEOFまで1行ずつ、タイムスタンプ等を付与せずそのまま書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = JstMidnightRotatingFileHandler(path, backup_count=retention_days)
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        for line in lines:
            try:
                # 末尾の改行はStreamHandler.terminatorが付けるため外す。
                record = logging.LogRecord("", logging.INFO, "", 0, line.rstrip("\r\n"), None, None)
                handler.handle(record)
            except Exception:
                # 書き出し失敗でローテータが落ちると、本体がSIGPIPEを受けて巻き込まれる。
                continue
    finally:
        handler.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--retention-days", type=int, default=None)
    args = parser.parse_args(argv)

    retention_days = args.retention_days
    if retention_days is None:
        try:
            retention_days = load_log_retention_days()
        except Exception as e:
            # 設定が読めなくてもローテータは落とさない（本体がSIGPIPEを受けるため）。
            # 設定ミスは本体側で起動時エラーになる。
            print(f"log_rotator: 保持日数を読めないため既定値を使います: {e}", file=sys.stderr)
            retention_days = DEFAULT_LOG_RETENTION_DAYS
    # 不正なUTF-8バイトでも落とさない。
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    rotate_stream(sys.stdin, args.path, max(1, retention_days))


if __name__ == "__main__":
    main()
