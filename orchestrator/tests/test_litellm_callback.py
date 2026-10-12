"""orchestrator.litellm_callback の単体テスト。

仕様: docs/basic-design.md 4章「LiteLLM Proxyの利用量計測」、issue #176

LiteLLM本体（`litellm[proxy]`）はオーケストレータ自身の依存ではない
（別プロセス・別venvで動かすネイティブ構成のため、pyproject.tomlにも追加しない）。
そのため`_build_usage_record`はLiteLLMの型に依存しない、dict-likeな
`kwargs`/`response_obj`で検証する。
"""

from __future__ import annotations

import asyncio

from orchestrator.litellm_callback import (
    PROXY_AGGREGATED_ISSUE_NUMBER,
    UNKNOWN_REPO,
    UsageStoreLogger,
    _is_ollama_backed_model,
    build_usage_record,
)


def test_build_usage_record_extracts_repo_from_model_info() -> None:
    kwargs = {
        "model": "project-a-ollama-qwen",
        "response_cost": 0.0,
        "litellm_params": {"model_info": {"repo": "nosetech/project-a"}},
    }
    response_obj = {"usage": {"prompt_tokens": 120, "completion_tokens": 40}}

    record = build_usage_record(kwargs, response_obj, is_error=False)

    assert record.repo == "nosetech/project-a"
    assert record.issue_number == PROXY_AGGREGATED_ISSUE_NUMBER
    assert record.model == "project-a-ollama-qwen"
    assert record.input_tokens == 120
    assert record.output_tokens == 40
    assert record.total_cost_usd == 0.0
    assert record.is_error is False


def test_build_usage_record_falls_back_to_unknown_repo_when_model_info_missing() -> None:
    record = build_usage_record({"model": "gpt-4o"}, {}, is_error=False)

    assert record.repo == UNKNOWN_REPO
    assert record.input_tokens == 0
    assert record.output_tokens == 0


def test_build_usage_record_reads_usage_from_object_attributes() -> None:
    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5

    class FakeResponse:
        usage = FakeUsage()

    kwargs = {"model": "m", "litellm_params": {"model_info": {"repo": "nosetech/project-a"}}}

    record = build_usage_record(kwargs, FakeResponse(), is_error=False)

    assert record.input_tokens == 10
    assert record.output_tokens == 5


def test_build_usage_record_marks_is_error() -> None:
    record = build_usage_record({"model": "m"}, {}, is_error=True)

    assert record.is_error is True


def test_usage_store_logger_records_via_store(monkeypatch) -> None:
    recorded = []
    monkeypatch.setattr(
        "orchestrator.litellm_callback.store_record_usage",
        lambda records, **kwargs: recorded.extend(records),
    )
    logger = UsageStoreLogger()

    logger._record(
        {"model": "m", "litellm_params": {"model_info": {"repo": "nosetech/project-a"}}},
        {"usage": {"prompt_tokens": 1, "completion_tokens": 2}},
        is_error=False,
    )

    assert len(recorded) == 1
    assert recorded[0].repo == "nosetech/project-a"


def test_usage_store_logger_swallows_recording_failures(monkeypatch) -> None:
    def _raise(records, **kwargs):
        raise RuntimeError("db error")

    monkeypatch.setattr("orchestrator.litellm_callback.store_record_usage", _raise)
    logger = UsageStoreLogger()

    # 例外を送出せず握りつぶすこと（LiteLLM Proxy本体のリクエスト処理を止めないため）。
    logger._record({"model": "m"}, {}, is_error=False)


def test_is_ollama_backed_model_true_for_ollama_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._get_router_deployments",
        lambda model_alias: [{"litellm_params": {"model": "ollama/deepseek-coder-v2:16b"}}],
    )

    assert _is_ollama_backed_model("project-a-ollama-deepseek") is True


def test_is_ollama_backed_model_true_for_ollama_chat_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._get_router_deployments",
        lambda model_alias: [{"litellm_params": {"model": "ollama_chat/qwen2.5-coder:7b"}}],
    )

    assert _is_ollama_backed_model("project-a-ollama-qwen") is True


def test_is_ollama_backed_model_false_for_non_ollama_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._get_router_deployments",
        lambda model_alias: [{"litellm_params": {"model": "openai/gpt-4o"}}],
    )

    assert _is_ollama_backed_model("project-a-openai-gpt4o") is False


def test_is_ollama_backed_model_false_when_no_deployment_found(monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._get_router_deployments", lambda model_alias: []
    )

    assert _is_ollama_backed_model("unknown-alias") is False


def test_pre_call_hook_drops_thinking_for_ollama_backed_anthropic_messages_request(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._is_ollama_backed_model", lambda model_alias: True
    )
    logger = UsageStoreLogger()
    data = {
        "model": "project-a-ollama-deepseek",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "messages": [{"role": "user", "content": "hi"}],
    }

    result = asyncio.run(logger.async_pre_call_hook(None, None, data, "anthropic_messages"))

    assert "thinking" not in result


def test_pre_call_hook_keeps_thinking_for_non_ollama_backed_anthropic_messages_request(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "orchestrator.litellm_callback._is_ollama_backed_model", lambda model_alias: False
    )
    logger = UsageStoreLogger()
    data = {
        "model": "project-a-openai-gpt4o",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }

    result = asyncio.run(logger.async_pre_call_hook(None, None, data, "anthropic_messages"))

    assert result["thinking"] == {"type": "enabled", "budget_tokens": 1024}


def test_pre_call_hook_ignores_non_anthropic_messages_call_types(monkeypatch) -> None:
    # issue #185で問題になるのは`/v1/messages`（call_type="anthropic_messages"）
    # 宛リクエストのみ。他のcall_type（例: "completion"）では`_is_ollama_backed_model`
    # を呼び出す必要すらないことを確認する。
    def _fail(model_alias: str) -> bool:
        raise AssertionError("call_type=anthropic_messages以外では呼ばれないはず")

    monkeypatch.setattr("orchestrator.litellm_callback._is_ollama_backed_model", _fail)
    logger = UsageStoreLogger()
    data = {
        "model": "project-a-ollama-deepseek",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }

    result = asyncio.run(logger.async_pre_call_hook(None, None, data, "completion"))

    assert result["thinking"] == {"type": "enabled", "budget_tokens": 1024}
