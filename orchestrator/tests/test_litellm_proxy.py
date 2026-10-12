"""orchestrator.litellm_proxy の単体テスト。

仕様: docs/basic-design.md 3-1「実行手段の切り替え」・4章、issue #176
"""

from __future__ import annotations

import urllib.error

import pytest

from orchestrator.config import EXECUTION_MODE_CLAUDE_CODE, EXECUTION_MODE_LITELLM_PROXY
from orchestrator.execution_mode import ExecutionSettings
from orchestrator.litellm_proxy import (
    DEFAULT_LITELLM_PROXY_URL,
    LITELLM_PROXY_API_KEY_ENV,
    LITELLM_PROXY_URL_ENV,
    build_env_overrides,
    is_healthy,
    resolve_api_key,
    resolve_base_url,
)


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_resolve_base_url_defaults_to_local_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LITELLM_PROXY_URL_ENV, raising=False)

    assert resolve_base_url() == DEFAULT_LITELLM_PROXY_URL


def test_resolve_base_url_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LITELLM_PROXY_URL_ENV, "http://127.0.0.1:5000")

    assert resolve_base_url() == "http://127.0.0.1:5000"


def test_resolve_api_key_defaults_to_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LITELLM_PROXY_API_KEY_ENV, raising=False)

    assert resolve_api_key() == ""


def test_is_healthy_returns_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: _FakeResponse(200))

    assert is_healthy("http://127.0.0.1:4000") is True


def test_is_healthy_returns_false_when_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, timeout: float) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    assert is_healthy("http://127.0.0.1:4000") is False


def test_is_healthy_returns_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, timeout: float) -> None:
        raise TimeoutError

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    assert is_healthy("http://127.0.0.1:4000") is False


def test_build_env_overrides_empty_for_claude_code() -> None:
    settings = ExecutionSettings(execution_mode=EXECUTION_MODE_CLAUDE_CODE, litellm_model=None)

    assert build_env_overrides(settings, base_url="http://x", api_key="k") == {}


def test_build_env_overrides_sets_anthropic_env_vars_for_litellm_proxy() -> None:
    settings = ExecutionSettings(
        execution_mode=EXECUTION_MODE_LITELLM_PROXY, litellm_model="ollama/qwen2.5-coder:7b"
    )

    env = build_env_overrides(settings, base_url="http://127.0.0.1:4000", api_key="sk-test")

    assert env == {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }
