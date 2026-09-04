"""orchestrator.litellm_callback の単体テスト。

仕様: docs/basic-design.md 4章「LiteLLM Proxyの利用量計測」、issue #176

LiteLLM本体（`litellm[proxy]`）はオーケストレータ自身の依存ではない
（別プロセス・別venvで動かすネイティブ構成のため、pyproject.tomlにも追加しない）。
そのため`_build_usage_record`はLiteLLMの型に依存しない、dict-likeな
`kwargs`/`response_obj`で検証する。
"""

from __future__ import annotations

from orchestrator.litellm_callback import (
    PROXY_AGGREGATED_ISSUE_NUMBER,
    UNKNOWN_REPO,
    UsageStoreLogger,
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
