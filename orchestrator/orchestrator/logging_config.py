"""orchestratorのロギング設定: レベル制御・フォーマット統一・日付ローテーション。

仕様: issue #114。従来は`server.py`等が`logging.getLogger(__name__)`のみを
呼び出し、ハンドラ・フォーマッタ・レベルを設定する`logging.basicConfig()`
相当の処理がどこにも存在しなかったため、実際にはPythonのデフォルト設定
（レベル`WARNING`以上・簡易フォーマット）で出力され、`logger.info()`/
`logger.debug()`呼び出しは実質握りつぶされていた。

`main.py`の`main()`冒頭で一度だけ`configure_logging()`を呼び出す。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.config import REPO_ROOT
from orchestrator.timezone import JST

# production/development切り替え用の環境変数。未設定時はproduction扱い
# （INFO以上のみ出力）とし、developmentを明示した場合のみDEBUG以上（全レベル）
# を出力する。bin/start.shは明示的な設定をせず起動するため、運用時は常に
# production相当となる。
ENV_VAR = "ORCHESTRATOR_ENV"
DEVELOPMENT = "development"

DEFAULT_LOG_PATH = REPO_ROOT / "logs" / "orchestrator.log"


class _JstFormatter(logging.Formatter):
    """`%(asctime)s`をOSのタイムゾーン設定に依存させず、常にJSTで出力する。

    デフォルトの`logging.Formatter.formatTime`は`time.localtime`（サーバーの
    OSタイムゾーン設定に依存）を使うため、実行環境によってJSTと一致しない
    ことがある。`usage_store.py`の`_JST`（issue #71）と同じ前例に合わせ、
    ログの日時もJST明示に統一する。
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=JST)
        if datefmt:
            return dt.strftime(datefmt)
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')},{int(record.msecs):03d}"


class JstMidnightRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """日次ローテーションの0時判定・世代ファイル名の日付をJSTに固定する。

    標準の`when="midnight"`は`time.localtime`（OSのタイムゾーン）で0時を判定する
    ため、OSがJST以外だとログ内の時刻（`_JstFormatter`）とファイルの区切りが
    ずれる（issue #254）。`orchestrator.log`・`dashboard.log`・
    `orchestrator.stderr.log`の3ファイルで共有する。
    """

    def __init__(self, filename: Path | str, *, backup_count: int) -> None:
        super().__init__(filename, when="midnight", backupCount=backup_count, encoding="utf-8")

    def computeRollover(self, currentTime: int) -> int:
        now = datetime.fromtimestamp(currentTime, tz=JST)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(next_midnight.timestamp())

    def rotation_filename(self, default_name: str) -> str:
        # doRollover()はrolloverAtを更新する前にこれを呼ぶ。rolloverAtの1秒前が
        # 「終わった日」（JST）にあたる。
        ended_day = datetime.fromtimestamp(self.rolloverAt - 1, tz=JST)
        return f"{self.baseFilename}.{ended_day.strftime('%Y-%m-%d')}"


def configure_logging(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    retention_days: int,
) -> None:
    """ルートロガーにJST・日次ローテーション対応のファイルハンドラを設定する。

    `TimedRotatingFileHandler(when="midnight", backupCount=retention_days)`が
    日付単位でのローテーション・保持世代数の管理を標準機能でまかなうため、
    自前でのファイル走査・削除は実装しない。二重書き込みを避けるため、
    コンソール向けの`StreamHandler`は追加しない（`bin/start.sh`が本体の
    stdout/stderrを`log_rotator.py`経由で`orchestrator.stderr.log`に書き出し、
    ロガーを経由しない出力・未捕捉例外向けの最終フォールバックとする）。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.get(ENV_VAR, "production")
    level = logging.DEBUG if env == DEVELOPMENT else logging.INFO

    handler = JstMidnightRotatingFileHandler(log_path, backup_count=retention_days)
    handler.setFormatter(_JstFormatter("%(asctime)s [%(levelname)s] %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # 二重呼び出し（テスト等）でハンドラが積み上がらないよう、既存ハンドラは
    # 一度クローズしてから設定し直す（close()せずclear()するだけだとファイル
    # ディスクリプタがリークする）。
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)
        existing_handler.close()
    root_logger.addHandler(handler)
