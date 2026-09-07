"""LiteLLM Proxyのカスタムコールバック: リクエスト完了時に`usage_store.py`へ統合記録する。

仕様: docs/basic-design.md 4章「LiteLLM Proxyの利用量計測」、issue #176

LiteLLM Proxyの設定ファイル（`config/litellm_config.yaml`）の
`litellm_settings.callbacks`に`orchestrator.litellm_callback.usage_store_logger`を
登録すると、LiteLLM Proxyプロセス自身がこのモジュールを`litellm.integrations.
custom_logger.CustomLogger`のインスタンスとしてロードし、リクエスト完了イベント
ごとに`async_log_success_event`/`async_log_failure_event`を呼び出す。

**repo単位の利用量帰属について**: LiteLLM ProxyはDBなし運用（PostgreSQL不使用、
basic-design.md 4章）のため、プロジェクトごとの仮想キー発行機能（`/key/generate`）
は使わない。そのため、単一の共有トークンでは「どのプロジェクトからのリクエスト
か」をトークン単位で区別できない。代わりに`config/litellm_config.yaml`の
`model_list`エントリで、プロジェクトごとに異なるモデルエイリアス（`model_name`）を
発行し、`model_info.repo`にリポジトリ名を埋め込む運用とする
（`agent_runner.py`が`Project.litellm_model`をこのエイリアス名として
`claude -p --model <alias>`に渡す）。これによりLiteLLM Proxy側は`model_info`から
repoを解決できる。

issue番号単位の帰属はこの仕組みでは得られない（1プロジェクトにつき1エイリアスの
ため）。Claude Code CLIは`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`経由の接続で
issue番号等の追加メタデータをリクエストに含める手段を持たないため、
`usage_records.issue_number`には代表値として`0`（実在しないissue番号、
「プロジェクト単位で集計されたLiteLLM Proxy経由の利用量」であることを示す
センチネル値）を記録する。ダッシュボードの日次・モデル別集計
（`usage_store.daily_model_usage`）はissue_numberを見ないため表示に影響しない。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from orchestrator.usage_store import UsageRecord
from orchestrator.usage_store import record_usage as store_record_usage

logger = logging.getLogger(__name__)

# 実在しないissue番号をセンチネル値として使う（モジュールdocstring参照）。
PROXY_AGGREGATED_ISSUE_NUMBER = 0

# `model_info.repo`が解決できない場合（config/litellm_config.yamlの記述漏れ等）の
# フォールバック値。
UNKNOWN_REPO = "unknown"

try:  # pragma: no cover - litellm本体はLiteLLM Proxyプロセス側にのみインストールされる
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:  # pragma: no cover
    # orchestrator本体（オーケストレータプロセス・そのテスト）は`litellm[proxy]`に
    # 依存しない（issue #176スコープの通り、LiteLLM Proxyはオーケストレータ自身とは
    # 別プロセス・別venvで動かすネイティブ構成のため）。このモジュール自体は
    # `_build_usage_record`の単体テストのためにimportできる必要があるので、
    # litellm未インストール環境でもimportエラーにならないよう最小限のフォールバック
    # 基底クラスを用意する。
    class CustomLogger:  # type: ignore[no-redef]
        pass


def _extract_repo(kwargs: dict[str, Any]) -> str:
    litellm_params = kwargs.get("litellm_params") or {}
    model_info = litellm_params.get("model_info") or kwargs.get("model_info") or {}
    repo = model_info.get("repo")
    return repo if isinstance(repo, str) and repo else UNKNOWN_REPO


def _extract_usage_tokens(response_obj: Any) -> tuple[int, int]:
    usage = getattr(response_obj, "usage", None)
    if usage is None and isinstance(response_obj, dict):
        usage = response_obj.get("usage")

    if usage is None:
        return 0, 0

    if isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
    else:
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

    return int(input_tokens), int(output_tokens)


def build_usage_record(kwargs: dict[str, Any], response_obj: Any, *, is_error: bool) -> UsageRecord:
    """LiteLLMコールバックの`kwargs`/`response_obj`から`UsageRecord`を組み立てる。

    LiteLLM本体の型（`ModelResponse`等）に依存せず、`usage`属性/キーを持つ
    dict-likeオブジェクトであれば動作するようにする（テスト容易性のため）。
    """
    repo = _extract_repo(kwargs)
    model = kwargs.get("model")
    model_name = model if isinstance(model, str) and model else "unknown"
    input_tokens, output_tokens = _extract_usage_tokens(response_obj)
    cost = kwargs.get("response_cost")

    return UsageRecord(
        repo=repo,
        issue_number=PROXY_AGGREGATED_ISSUE_NUMBER,
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost_usd=cost if isinstance(cost, int | float) else None,
        is_error=is_error,
    )


class UsageStoreLogger(CustomLogger):
    """`config/litellm_config.yaml`の`litellm_settings.callbacks`に登録するクラス。"""

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time) -> None:
        self._record(kwargs, response_obj, is_error=False)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time) -> None:
        self._record(kwargs, response_obj, is_error=True)

    def _record(self, kwargs: dict[str, Any], response_obj: Any, *, is_error: bool) -> None:
        try:
            record = build_usage_record(kwargs, response_obj, is_error=is_error)
            store_record_usage([record], now=lambda: datetime.now(UTC))
        except Exception:
            # コールバックの失敗でLiteLLM Proxy自体のリクエスト処理を止めないよう、
            # 利用量記録の失敗はログ警告に留めて握りつぶす（可視化のみを目的とする
            # 機能のため。basic-design.md 4章「予算上限のハード制限は導入しない」と
            # 同じ「可視化を阻害しても本処理は止めない」方針）。
            logger.warning("LiteLLM Proxyの利用量記録に失敗しました。", exc_info=True)


# `litellm_config.yaml`の`callbacks`はモジュールパス文字列でクラス/インスタンスを
# 参照する。LiteLLM側の実装はクラスの新規インスタンス化・インスタンス直接参照の
# どちらの記法にも対応しているため、両方使えるようインスタンスもエクスポートする。
usage_store_logger = UsageStoreLogger()
