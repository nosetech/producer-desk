"""LiteLLM Proxyへの接続設定・死活監視（issue #176）。

仕様: docs/basic-design.md 3-1「実行手段の切り替え」・4章
Claude Code CLIは環境変数`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`で接続先を
LiteLLM Proxyへ切り替えられる（`ANTHROPIC_BASE_URL`設定時はサブスクリプション
OAuthではなく静的トークン認証になる）。
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request

from orchestrator.config import EXECUTION_MODE_LITELLM_PROXY
from orchestrator.execution_mode import ExecutionSettings

logger = logging.getLogger(__name__)

# LiteLLM Proxyのエンドポイント（ネイティブ構成でローカルPC上に導入、既定ポート
# 4000）。環境変数で上書きできる（複数インスタンス運用・開発時の切り替え用）。
LITELLM_PROXY_URL_ENV = "LITELLM_PROXY_URL"
DEFAULT_LITELLM_PROXY_URL = "http://127.0.0.1:4000"

# LiteLLM Proxy自体はDBなし運用（basic-design.md 4章）のため、プロジェクトごとの
# 仮想キー発行機能は使わない。同一LAN内アクセスのみを前提とするネットワーク境界
# （CLAUDE.md「確定済みの設計判断」）に保護を委ね、`ANTHROPIC_AUTH_TOKEN`には
# この単一の共有トークンを使う（未設定時は空文字列 = 認証無し構成のLiteLLM Proxy
# を想定）。
LITELLM_PROXY_API_KEY_ENV = "LITELLM_PROXY_API_KEY"

# `/health/liveliness`はLiteLLM Proxyプロセス自体が生きているかのみを確認する
# 軽量なエンドポイント（`/health`は配下の全モデルへの疎通確認を伴い遅い・エラーに
# なりやすいため使わない）。
_HEALTH_PATH = "/health/liveliness"


def resolve_base_url() -> str:
    return os.environ.get(LITELLM_PROXY_URL_ENV, DEFAULT_LITELLM_PROXY_URL)


def resolve_api_key() -> str:
    return os.environ.get(LITELLM_PROXY_API_KEY_ENV, "")


def is_healthy(base_url: str, *, timeout: float = 3.0) -> bool:
    """LiteLLM Proxyプロセスが応答するかを確認する。

    プロセスが落ちている・応答しない場合、Agent Runner側は(A) Claude Code CLI
    直利用へ自動フォールバックする（`agent_runner.run_agent_runner`参照）。
    """
    try:
        with urllib.request.urlopen(f"{base_url}{_HEALTH_PATH}", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def build_env_overrides(
    settings: ExecutionSettings, *, base_url: str, api_key: str
) -> dict[str, str]:
    """`subprocess.Popen`に渡す環境変数の追加分を返す。

    (A) Claude Code CLI直利用の場合は空dict（既存の環境変数をそのまま使い、
    サブスクリプションOAuth認証のまま起動する）。
    """
    if settings.execution_mode != EXECUTION_MODE_LITELLM_PROXY:
        return {}
    return {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": api_key}
