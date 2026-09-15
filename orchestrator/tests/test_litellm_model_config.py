"""orchestrator.litellm_model_config の単体テスト。

docs/basic-design.md 4章「オーケストレータ側での会話量・ターン数上限による
セッションリセット（issue #189）」を検証する。max_session_tokens/
max_session_turnsは、config/litellm_config.yamlのmodel_list[].model_infoに
（num_ctxと同じくモデル単位で）定義される。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.litellm_model_config import SessionGuardSettings, resolve_session_guard_settings

_CONFIG_YAML = """
model_list:
  - model_name: project-a-openai-gpt4o
    litellm_params:
      model: openai/gpt-4o
    model_info:
      repo: nosetech/project-a
  - model_name: project-b-ollama-qwen
    litellm_params:
      model: ollama/qwen2.5-coder:7b
      num_ctx: 32768
    model_info:
      repo: nosetech/project-b
      max_session_tokens: 24000
      max_session_turns: 20
  - model_name: project-c-ollama-no-limits
    litellm_params:
      model: ollama/deepseek-coder-v2:16b
    model_info:
      repo: nosetech/project-c
"""


def test_resolve_session_guard_settings_returns_empty_when_file_does_not_exist(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "does-not-exist.yaml"

    assert resolve_session_guard_settings(
        "project-b-ollama-qwen", config_path=config_path
    ) == SessionGuardSettings(None, None)


def test_resolve_session_guard_settings_returns_none_when_litellm_model_is_none(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "litellm_config.yaml"
    config_path.write_text(_CONFIG_YAML, encoding="utf-8")

    assert resolve_session_guard_settings(None, config_path=config_path) == SessionGuardSettings(
        None, None
    )


def test_resolve_session_guard_settings_reads_matching_model_info(tmp_path: Path) -> None:
    config_path = tmp_path / "litellm_config.yaml"
    config_path.write_text(_CONFIG_YAML, encoding="utf-8")

    result = resolve_session_guard_settings("project-b-ollama-qwen", config_path=config_path)

    assert result == SessionGuardSettings(max_session_tokens=24000, max_session_turns=20)


def test_resolve_session_guard_settings_returns_none_when_model_info_omits_limits(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "litellm_config.yaml"
    config_path.write_text(_CONFIG_YAML, encoding="utf-8")

    result = resolve_session_guard_settings("project-c-ollama-no-limits", config_path=config_path)

    assert result == SessionGuardSettings(None, None)


def test_resolve_session_guard_settings_returns_empty_when_model_name_not_found(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "litellm_config.yaml"
    config_path.write_text(_CONFIG_YAML, encoding="utf-8")

    result = resolve_session_guard_settings("no-such-model", config_path=config_path)

    assert result == SessionGuardSettings(None, None)
