"""orchestrator.session_store の単体テスト。

docs/basic-design.md 3-1（初回ディスパッチ時にセッションIDをconfig/projects.yamlへ
書き戻す）を検証する。PyYAMLで全体を再シリアライズせず、対象repoブロックの
session_id行だけをテキスト差分で置換する挙動を確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.session_store import persist_session_id, update_session_id

SAMPLE_YAML = """\
projects:
  - repo: nosetech/project-a
    worktree_path: /Users/producer/worktrees/project-a
    session_id: null   # 初回ディスパッチ後に自動採番・保存
  - repo: nosetech/project-b
    worktree_path: /Users/producer/worktrees/project-b
    session_id: null
"""


def test_update_session_id_replaces_null_value_preserving_comment() -> None:
    updated = update_session_id(SAMPLE_YAML, "nosetech/project-a", "abc-123")

    lines = updated.splitlines()
    assert '    session_id: "abc-123"   # 初回ディスパッチ後に自動採番・保存' in lines
    # project-bのブロックは変更されない
    assert "    session_id: null" in lines


def test_update_session_id_only_touches_target_repo_block() -> None:
    updated = update_session_id(SAMPLE_YAML, "nosetech/project-b", "xyz-789")

    lines = updated.splitlines()
    assert '    session_id: "xyz-789"' in lines
    assert "    session_id: null   # 初回ディスパッチ後に自動採番・保存" in lines


def test_update_session_id_replaces_existing_quoted_value() -> None:
    yaml_with_existing_session = """\
projects:
  - repo: nosetech/project-a
    worktree_path: /tmp/project-a
    session_id: "old-session-id"
"""
    updated = update_session_id(yaml_with_existing_session, "nosetech/project-a", "new-session-id")

    assert '    session_id: "new-session-id"' in updated
    assert "old-session-id" not in updated


def test_update_session_id_preserves_all_other_lines_unchanged() -> None:
    updated = update_session_id(SAMPLE_YAML, "nosetech/project-a", "abc-123")

    original_lines = SAMPLE_YAML.splitlines()
    updated_lines = updated.splitlines()
    assert len(original_lines) == len(updated_lines)

    changed = [
        (original, new) for original, new in zip(original_lines, updated_lines) if original != new
    ]
    assert changed == [
        (
            "    session_id: null   # 初回ディスパッチ後に自動採番・保存",
            '    session_id: "abc-123"   # 初回ディスパッチ後に自動採番・保存',
        )
    ]


def test_update_session_id_unknown_repo_raises() -> None:
    with pytest.raises(ValueError):
        update_session_id(SAMPLE_YAML, "nosetech/unknown", "abc-123")


def test_persist_session_id_writes_back_to_file(tmp_path: Path) -> None:
    config_path = tmp_path / "projects.yaml"
    config_path.write_text(SAMPLE_YAML, encoding="utf-8")

    persist_session_id("nosetech/project-a", "abc-123", config_path=config_path)

    content = config_path.read_text(encoding="utf-8")
    assert '    session_id: "abc-123"   # 初回ディスパッチ後に自動採番・保存' in content
