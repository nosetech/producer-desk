"""orchestrator.execution_mode の単体テスト。

仕様: docs/basic-design.md 4章「issueコメントでの都度指示」、issue #176
"""

from __future__ import annotations

from orchestrator.config import EXECUTION_MODE_CLAUDE_CODE, EXECUTION_MODE_LITELLM_PROXY, Project
from orchestrator.execution_mode import (
    ExecutionSettings,
    parse_override_directive,
    resolve_execution_settings,
    strip_override_directive,
)


def test_parse_override_directive_detects_litellm_alias() -> None:
    settings = parse_override_directive(
        "対応してください\n/model litellm:ollama/qwen2.5-coder:7b\n"
    )

    assert settings == ExecutionSettings(
        execution_mode=EXECUTION_MODE_LITELLM_PROXY, litellm_model="ollama/qwen2.5-coder:7b"
    )


def test_parse_override_directive_detects_claude_code_revert() -> None:
    settings = parse_override_directive("いつも通りお願いします\n/model claude_code\n")

    assert settings == ExecutionSettings(
        execution_mode=EXECUTION_MODE_CLAUDE_CODE, litellm_model=None
    )


def test_parse_override_directive_returns_none_when_absent() -> None:
    assert parse_override_directive("普通の指示です") is None


def test_parse_override_directive_ignores_directive_mentioned_mid_sentence() -> None:
    # 行頭以外（他の文章の途中）に現れた場合は誤検知しない。
    assert parse_override_directive("設定として /model litellm:foo を使ってください") is None


def test_parse_override_directive_uses_last_occurrence_when_repeated() -> None:
    message = "/model litellm:foo\n訂正します\n/model litellm:bar\n"

    settings = parse_override_directive(message)

    assert settings.litellm_model == "bar"


def test_strip_override_directive_removes_directive_line_only() -> None:
    message = "対応してください\n/model litellm:ollama/qwen2.5-coder:7b\n続きの指示です"

    stripped = strip_override_directive(message)

    assert "/model" not in stripped
    assert "対応してください" in stripped
    assert "続きの指示です" in stripped


def test_resolve_execution_settings_prefers_message_directive_and_persists_it() -> None:
    project = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")
    persisted: list[tuple] = []

    settings, message = resolve_execution_settings(
        project,
        "nosetech/project-a",
        1,
        "/model litellm:ollama/qwen2.5-coder:7b\n本文",
        get_execution_override_fn=lambda repo, issue_number: None,
        persist_execution_override_fn=lambda *args: persisted.append(args),
    )

    assert settings.execution_mode == EXECUTION_MODE_LITELLM_PROXY
    assert settings.litellm_model == "ollama/qwen2.5-coder:7b"
    assert "/model" not in message
    assert persisted == [
        ("nosetech/project-a", 1, EXECUTION_MODE_LITELLM_PROXY, "ollama/qwen2.5-coder:7b")
    ]


def test_resolve_execution_settings_uses_fallback_message_for_directive_only_comment() -> None:
    project = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")

    settings, message = resolve_execution_settings(
        project,
        "nosetech/project-a",
        1,
        "/model litellm:ollama/qwen2.5-coder:7b",
        get_execution_override_fn=lambda repo, issue_number: None,
        persist_execution_override_fn=lambda *args: None,
    )

    assert settings.litellm_model == "ollama/qwen2.5-coder:7b"
    assert message != ""
    assert "/model" not in message


def test_resolve_execution_settings_falls_back_to_stored_override_when_no_directive() -> None:
    project = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")

    settings, message = resolve_execution_settings(
        project,
        "nosetech/project-a",
        1,
        "続きの指示です",
        get_execution_override_fn=lambda repo, issue_number: {
            "execution_mode": EXECUTION_MODE_LITELLM_PROXY,
            "litellm_model": "ollama/qwen2.5-coder:7b",
        },
        persist_execution_override_fn=lambda *args: (_ for _ in ()).throw(
            AssertionError("永続化は呼ばれないはず")
        ),
    )

    assert settings.execution_mode == EXECUTION_MODE_LITELLM_PROXY
    assert settings.litellm_model == "ollama/qwen2.5-coder:7b"
    assert message == "続きの指示です"


def test_resolve_execution_settings_falls_back_to_project_default_when_nothing_stored() -> None:
    project = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")

    settings, message = resolve_execution_settings(
        project,
        "nosetech/project-a",
        1,
        "続きの指示です",
        get_execution_override_fn=lambda repo, issue_number: None,
        persist_execution_override_fn=lambda *args: (_ for _ in ()).throw(
            AssertionError("永続化は呼ばれないはず")
        ),
    )

    assert settings.execution_mode == EXECUTION_MODE_CLAUDE_CODE
    assert settings.litellm_model is None
    assert message == "続きの指示です"
