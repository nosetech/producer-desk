"""orchestrator.ollama_bench の単体テスト。

MCP `ollama-client` ではOllama REST APIの`prompt_eval_count`/`eval_count`/
`total_duration`等が取得できないため、直接REST APIを叩く手動ベンチマーク
ツールを検証する（issue #60コメント参照）。実ネットワークは叩かず、
`http_post`をDIで差し替える。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.ollama_bench import (
    DEFAULT_OLLAMA_HOST,
    call_ollama_chat,
    resolve_ollama_host,
    to_usage_record,
)
from orchestrator.usage_store import UsageRecord, daily_model_usage, record_usage


class FakeHttpPost:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, url: str, payload: bytes, **kwargs: object) -> dict:
        self.calls.append({"url": url, "payload": payload, **kwargs})
        return self.response


OLLAMA_CHAT_RESPONSE = {
    "message": {"role": "assistant", "content": "def foo(): ..."},
    "prompt_eval_count": 845,
    "eval_count": 634,
    "total_duration": 12_500_000_000,
    "load_duration": 500_000_000,
    "prompt_eval_duration": 2_000_000_000,
    "eval_duration": 10_000_000_000,
}


def test_resolve_ollama_host_prefers_explicit_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://192.168.10.121:11434")

    assert resolve_ollama_host("http://explicit:11434") == "http://explicit:11434"


def test_resolve_ollama_host_falls_back_to_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://192.168.10.121:11434")

    assert resolve_ollama_host(None) == "http://192.168.10.121:11434"


def test_resolve_ollama_host_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    assert resolve_ollama_host(None) == DEFAULT_OLLAMA_HOST


def test_call_ollama_chat_parses_real_metrics_from_response() -> None:
    http_post = FakeHttpPost(OLLAMA_CHAT_RESPONSE)

    result = call_ollama_chat(
        "deepseek-coder-v2:16b",
        "implement usage_store.py",
        host="http://192.168.10.121:11434",
        http_post=http_post,
    )

    assert result.model == "deepseek-coder-v2:16b"
    assert result.prompt_tokens == 845
    assert result.completion_tokens == 634
    assert result.total_duration_ns == 12_500_000_000
    assert result.eval_duration_ns == 10_000_000_000
    assert result.response_text == "def foo(): ..."
    assert http_post.calls[0]["url"] == "http://192.168.10.121:11434/api/chat"


def test_call_ollama_chat_posts_system_message_when_given() -> None:
    http_post = FakeHttpPost(OLLAMA_CHAT_RESPONSE)

    call_ollama_chat(
        "gemma2",
        "docsを書いて",
        host="http://host:11434",
        system="あなたは...",
        http_post=http_post,
    )

    body = json.loads(http_post.calls[0]["payload"])
    assert body["messages"][0] == {"role": "system", "content": "あなたは..."}
    assert body["messages"][1] == {"role": "user", "content": "docsを書いて"}
    assert body["stream"] is False


def test_to_usage_record_converts_tokens_and_duration() -> None:
    result = call_ollama_chat(
        "deepseek-coder-v2:16b",
        "prompt",
        host="http://host:11434",
        http_post=FakeHttpPost(OLLAMA_CHAT_RESPONSE),
    )

    record = to_usage_record(result, repo="nosetech/producer-desk", issue_number=60)

    assert record == UsageRecord(
        repo="nosetech/producer-desk",
        issue_number=60,
        model="deepseek-coder-v2:16b",
        input_tokens=845,
        output_tokens=634,
        duration_seconds=12.5,
    )


def test_benchmark_result_can_be_recorded_and_aggregated_via_usage_store(tmp_path: Path) -> None:
    """issue #60で作ったconfig/usage.dbにベンチマーク結果を統合して記録できることを確認する。"""
    db_path = tmp_path / "usage.db"
    result = call_ollama_chat(
        "deepseek-coder-v2:16b",
        "prompt",
        host="http://host:11434",
        http_post=FakeHttpPost(OLLAMA_CHAT_RESPONSE),
    )
    record = to_usage_record(result, repo="nosetech/producer-desk", issue_number=60)

    record_usage([record], db_path=db_path)

    daily = daily_model_usage(db_path=db_path, today=datetime.now(UTC).date())
    assert len(daily) == 1
    assert daily[0].model == "deepseek-coder-v2:16b"
    assert daily[0].input_tokens == 845
    assert daily[0].output_tokens == 634
