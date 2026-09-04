"""orchestrator.execution_override_store の単体テスト。

`orchestrator.session_store`と同様、issue単位でJSONファイルに永続化することを
検証する（docs/basic-design.md 4章「issueコメントでの都度指示」、issue #176）。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.execution_override_store import (
    EXECUTION_OVERRIDES_PATH_ENV,
    get_execution_override,
    persist_execution_override,
)


def test_get_execution_override_returns_none_when_file_absent(tmp_path: Path) -> None:
    overrides_path = tmp_path / "execution_overrides.json"

    assert get_execution_override("nosetech/project-a", 1, overrides_path=overrides_path) is None


def test_persist_and_get_execution_override_round_trip(tmp_path: Path) -> None:
    overrides_path = tmp_path / "execution_overrides.json"

    persist_execution_override(
        "nosetech/project-a",
        1,
        "litellm_proxy",
        "ollama/qwen2.5-coder:7b",
        overrides_path=overrides_path,
    )

    assert get_execution_override("nosetech/project-a", 1, overrides_path=overrides_path) == {
        "execution_mode": "litellm_proxy",
        "litellm_model": "ollama/qwen2.5-coder:7b",
    }


def test_persist_execution_override_is_scoped_per_issue(tmp_path: Path) -> None:
    overrides_path = tmp_path / "execution_overrides.json"

    persist_execution_override(
        "nosetech/project-a", 1, "litellm_proxy", "model-a", overrides_path=overrides_path
    )
    persist_execution_override(
        "nosetech/project-a", 2, "claude_code", None, overrides_path=overrides_path
    )

    assert get_execution_override("nosetech/project-a", 1, overrides_path=overrides_path) == {
        "execution_mode": "litellm_proxy",
        "litellm_model": "model-a",
    }
    assert get_execution_override("nosetech/project-a", 2, overrides_path=overrides_path) == {
        "execution_mode": "claude_code",
        "litellm_model": None,
    }


def test_execution_overrides_path_env_var_used_when_arg_omitted(
    monkeypatch, tmp_path: Path
) -> None:
    overrides_path = tmp_path / "dev-execution-overrides.json"
    monkeypatch.setenv(EXECUTION_OVERRIDES_PATH_ENV, str(overrides_path))

    persist_execution_override("nosetech/project-a", 1, "claude_code", None)

    assert overrides_path.exists()
    assert get_execution_override("nosetech/project-a", 1) == {
        "execution_mode": "claude_code",
        "litellm_model": None,
    }
