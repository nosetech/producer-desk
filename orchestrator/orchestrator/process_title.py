"""orchestratorのプロセス名をpsで判別できる固有名にする（issue #332）。

`python -m orchestrator.main`で起動するとps上は`python ...`と表示され、同一ホストの
他のPythonプロセスと見分けにくい。環境変数`ORCHESTRATOR_PROCESS_NAME`（未設定時は
`producer-desk-orchestrator`、空文字なら変更しない）で`setproctitle`により設定する。

`setproctitle`はC拡張のため、未インストール環境でも起動できるよう必須にはせず、
ImportError時は警告ログのみ出して継続する。プロセス名は人間がpsで見分けるための
もので、停止処理は従来どおりPIDファイルで行う。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

logger = logging.getLogger(__name__)

PROCESS_NAME_ENV = "ORCHESTRATOR_PROCESS_NAME"
DEFAULT_PROCESS_NAME = "producer-desk-orchestrator"


def resolve_process_name(env: Mapping[str, str] | None = None) -> str | None:
    """設定するプロセス名を返す。空文字が指定された場合はNone（変更しない）。"""
    if env is None:
        env = os.environ
    value = env.get(PROCESS_NAME_ENV)
    if value is None:
        return DEFAULT_PROCESS_NAME
    value = value.strip()
    return value or None


def apply_process_name(env: Mapping[str, str] | None = None) -> str | None:
    """プロセス名を設定し、設定した名前を返す（設定しなかった場合はNone）。

    例外は送出しない（プロセス名の設定失敗で起動を止めない）。
    """
    name = resolve_process_name(env)
    if name is None:
        return None
    try:
        import setproctitle
    except ImportError:
        logger.warning(
            "setproctitleがインストールされていないため、プロセス名を%sに設定できません"
            "（pip install -e . で導入できます）",
            name,
        )
        return None
    try:
        setproctitle.setproctitle(name)
    except Exception:
        logger.warning("プロセス名を%sに設定できませんでした", name, exc_info=True)
        return None
    logger.info("プロセス名を%sに設定しました", name)
    return name
