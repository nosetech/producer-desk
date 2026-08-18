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
from datetime import datetime
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


def configure_logging(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    retention_days: int,
) -> None:
    """ルートロガーにJST・日次ローテーション対応のファイルハンドラを設定する。

    `TimedRotatingFileHandler(when="midnight", backupCount=retention_days)`が
    日付単位でのローテーション・保持世代数の管理を標準機能でまかなうため、
    自前でのファイル走査・削除は実装しない。二重書き込みを避けるため、
    コンソール向けの`StreamHandler`は追加しない（`bin/start.sh`側の生
    リダイレクトが、ロガーを経由しない出力・未捕捉例外向けの最終フォール
    バックとして別途残る）。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.get(ENV_VAR, "production")
    level = logging.DEBUG if env == DEVELOPMENT else logging.INFO

    handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=retention_days, encoding="utf-8"
    )
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
