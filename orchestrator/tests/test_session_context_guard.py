"""orchestrator.session_context_guard の単体テスト。

docs/basic-design.md 4章「オーケストレータ側での会話量・ターン数上限による
セッションリセット（issue #189）」を検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.session_context_guard import (
    read_latest_context_tokens,
    resolve_transcript_path,
)


def _assistant_line(input_tokens: int, cache_creation: int, cache_read: int) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                },
            },
        }
    )


def test_resolve_transcript_path_escapes_worktree_path_slashes(tmp_path: Path) -> None:
    worktree_path = tmp_path / "worktrees" / "project-a"
    worktree_path.mkdir(parents=True)
    claude_projects_dir = tmp_path / ".claude" / "projects"

    result = resolve_transcript_path(
        worktree_path, "session-1", claude_projects_dir=claude_projects_dir
    )

    escaped = str(worktree_path.resolve()).replace("/", "-")
    assert result == claude_projects_dir / escaped / "session-1.jsonl"


def test_read_latest_context_tokens_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert read_latest_context_tokens(tmp_path / "does-not-exist.jsonl") is None


def test_read_latest_context_tokens_sums_last_assistant_usage(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session-1.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                _assistant_line(1000, 0, 0),
                json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
                _assistant_line(500, 200, 30000),
            ]
        ),
        encoding="utf-8",
    )

    assert read_latest_context_tokens(transcript_path) == 500 + 200 + 30000


def test_read_latest_context_tokens_skips_blank_and_malformed_lines(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session-1.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                _assistant_line(100, 0, 0),
                "",
                "not valid json",
                "   ",
            ]
        ),
        encoding="utf-8",
    )

    assert read_latest_context_tokens(transcript_path) == 100


def test_read_latest_context_tokens_returns_none_when_no_assistant_usage_line(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "session-1.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        encoding="utf-8",
    )

    assert read_latest_context_tokens(transcript_path) is None


def test_read_latest_context_tokens_ignores_assistant_line_without_usage(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "session-1.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                _assistant_line(100, 0, 0),
                json.dumps({"type": "assistant", "message": {"role": "assistant"}}),
            ]
        ),
        encoding="utf-8",
    )

    assert read_latest_context_tokens(transcript_path) == 100
