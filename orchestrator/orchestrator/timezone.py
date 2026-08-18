"""JST（Asia/Tokyo）タイムゾーンの共有定義。

ログ出力（`logging_config.py`・`agent_runner.py`）・利用量集計（`usage_store.py`の
`_JST`、issue #71）など、OSのタイムゾーン設定に依存させたくない日時処理から
共通で参照する（issue #114）。
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
