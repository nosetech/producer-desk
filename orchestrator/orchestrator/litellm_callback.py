"""LiteLLM Proxyのカスタムコールバック: リクエスト完了時に`usage_store.py`へ統合記録する。

仕様: docs/basic-design.md 4章「LiteLLM Proxyの利用量計測」、issue #176・#185

LiteLLM Proxyの設定ファイル（`config/litellm_config.yaml`）の
`litellm_settings.callbacks`に`orchestrator.litellm_callback.usage_store_logger`を
登録すると、LiteLLM Proxyプロセス自身がこのモジュールを`litellm.integrations.
custom_logger.CustomLogger`のインスタンスとしてロードし、リクエスト完了イベント
ごとに`async_log_success_event`/`async_log_failure_event`を呼び出す。加えて
`async_pre_call_hook`（issue #185、後述）も同じ登録で呼び出される。

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


# issue #185: AnthropicのMessages API（`thinking`パラメータ）を使うクライアント
# （Claude Code CLIが`ANTHROPIC_BASE_URL`経由でLiteLLM Proxyの`/v1/messages`に
# 送るリクエストがこれにあたる。会話が長くなり自動コンテキスト圧縮（compaction）が
# 発生すると、Claude Code CLIは必ずこのパラメータを付与する）を、`think`機能を
# 持たないOllamaモデルへそのまま中継すると、Ollama自体が
# `"<model>" does not support thinking`という400エラーを返し、compactionが
# 失敗してセッション全体が異常終了する。
#
# `litellm_settings.drop_params: true`はこれを解決しない（実機検証済み）。
# `/v1/messages`エンドポイントの実装（`litellm.llms.anthropic.
# experimental_pass_through.messages`）は、通常のchat/completions系リクエストが
# 通る`litellm.utils.get_optional_params`のOpenAI形式パラメータ検証・ドロップ経路
# （`drop_params`はここでのみ働く）を通らず、`thinking`をOllamaへそのまま転送する
# ため。そのため本コールバックの`async_pre_call_hook`で、Ollama系プロバイダ
# （`ollama/`・`ollama_chat/`）宛のリクエストに限り`thinking`パラメータ自体を
# 事前に取り除く。Ollama以外のバックエンド（OpenAI等、拡張思考に対応しうる）は
# 対象外とし、既存の拡張思考機能を損なわない。
_OLLAMA_LITELLM_PROVIDER_PREFIXES = ("ollama/", "ollama_chat/")


def _get_router_deployments(model_alias: str) -> list[dict[str, Any]]:
    """LiteLLM Proxyの`llm_router`から、モデルエイリアスに紐づくデプロイメント一覧を取得する。

    LiteLLM本体はLiteLLM Proxyプロセス側にのみインストールされるため
    （モジュールdocstring参照）、orchestrator本体の単体テスト環境ではこの関数
    自体をモックする（test_litellm_callback.py参照）。
    """
    try:
        from litellm.proxy.proxy_server import llm_router
    except (
        ImportError
    ):  # pragma: no cover - litellm本体はLiteLLM Proxyプロセス側にのみインストールされる
        return []
    if llm_router is None:
        return []
    try:
        return llm_router.get_model_list(model_name=model_alias) or []
    except Exception:
        logger.warning("LiteLLM Proxyのモデル一覧取得に失敗しました。", exc_info=True)
        return []


def _is_ollama_backed_model(model_alias: str) -> bool:
    for deployment in _get_router_deployments(model_alias):
        litellm_params = deployment.get("litellm_params") or {}
        target_model = litellm_params.get("model")
        if isinstance(target_model, str) and target_model.startswith(
            _OLLAMA_LITELLM_PROVIDER_PREFIXES
        ):
            return True
    return False


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

    async def async_pre_call_hook(
        self, user_api_key_dict, cache, data, call_type
    ) -> dict[str, Any]:
        # issue #185: `anthropic_messages`は`/v1/messages`（Anthropic Messages API
        # 互換）宛リクエストのcall_type。Claude Code CLIが`ANTHROPIC_BASE_URL`経由で
        # 送るリクエストはすべてこの形式になる（`_is_ollama_backed_model`直前の
        # コメント参照）。
        if call_type == "anthropic_messages" and "thinking" in data:
            model_alias = data.get("model")
            if isinstance(model_alias, str) and _is_ollama_backed_model(model_alias):
                data.pop("thinking", None)
                logger.info(
                    "Ollama系モデル(%s)宛リクエストから非対応の'thinking'パラメータを除去しました"
                    "（issue #185）。",
                    model_alias,
                )
        return data

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
