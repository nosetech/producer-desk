"""定型文の永続化（issue #323）のテスト。"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from orchestrator.snippets import (
    MAX_BODY_LENGTH,
    MAX_SNIPPETS,
    MAX_TITLE_LENGTH,
    SnippetNotFoundError,
    SnippetOrderConflictError,
    SnippetStorageError,
    SnippetValidationError,
    create_snippet,
    delete_snippet,
    load_snippets,
    load_snippets_safe,
    reorder_snippets,
    update_snippet,
    validate_snippet,
)


def test_load_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_snippets(tmp_path / "none.yaml") == []


def test_create_appends_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    a = create_snippet("  方針OK ", "この方針で進めて", path)
    b = create_snippet("テスト", "まずテストを追加して", path)

    assert a["title"] == "方針OK"
    assert a["id"] != b["id"]
    assert [s["id"] for s in load_snippets(path)] == [a["id"], b["id"]]
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(data) == ["snippets"]


def test_update_keeps_order_and_changes_fields(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    a = create_snippet("A", "a", path)
    b = create_snippet("B", "b", path)

    updated = update_snippet(a["id"], "A2", "a2\n二行目", path)

    assert updated == {"id": a["id"], "title": "A2", "body": "a2\n二行目"}
    assert [s["title"] for s in load_snippets(path)] == ["A2", "B"]
    assert load_snippets(path)[1] == b


def test_update_and_delete_unknown_id_raise(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    with pytest.raises(SnippetNotFoundError):
        update_snippet("abc", "t", "b", path)
    with pytest.raises(SnippetNotFoundError):
        delete_snippet("abc", path)


def test_delete_removes_only_target(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    a = create_snippet("A", "a", path)
    b = create_snippet("B", "b", path)

    remaining = delete_snippet(a["id"], path)

    assert remaining == [b]
    assert load_snippets(path) == [b]


def test_reorder_requires_exact_id_set(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    a = create_snippet("A", "a", path)
    b = create_snippet("B", "b", path)
    c = create_snippet("C", "c", path)

    ordered = reorder_snippets([c["id"], a["id"], b["id"]], path)
    assert [s["title"] for s in ordered] == ["C", "A", "B"]
    assert [s["title"] for s in load_snippets(path)] == ["C", "A", "B"]

    for bad in ([a["id"], b["id"]], [a["id"], a["id"], b["id"]], [a["id"], b["id"], "zzz"]):
        with pytest.raises(SnippetOrderConflictError):
            reorder_snippets(bad, path)
    with pytest.raises(SnippetValidationError):
        reorder_snippets("x", path)
    assert [s["title"] for s in load_snippets(path)] == ["C", "A", "B"]


@pytest.mark.parametrize(
    ("title", "body", "message"),
    [
        ("", "b", "タイトルが空です"),
        ("   ", "b", "タイトルが空です"),
        ("a\nb", "b", "タイトルに改行は使用できません"),
        ("x" * (MAX_TITLE_LENGTH + 1), "b", f"タイトルは{MAX_TITLE_LENGTH}文字以内"),
        ("x" * MAX_TITLE_LENGTH + " ", "b", f"タイトルは{MAX_TITLE_LENGTH}文字以内"),
        ("t", " \n ", "本文が空です"),
        ("t", "x" * (MAX_BODY_LENGTH + 1), f"本文は{MAX_BODY_LENGTH}文字以内"),
        (None, "b", "タイトルは文字列"),
        ("t", 1, "本文は文字列"),
    ],
)
def test_validate_rejects_invalid(title: object, body: object, message: str) -> None:
    errors = validate_snippet(title, body)
    assert any(message in e for e in errors)


def test_validate_accepts_limits() -> None:
    assert validate_snippet("x" * MAX_TITLE_LENGTH, "y" * MAX_BODY_LENGTH) == []


def test_create_rejects_over_limit(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    for i in range(MAX_SNIPPETS):
        create_snippet(f"t{i}", "b", path)
    with pytest.raises(SnippetValidationError):
        create_snippet("over", "b", path)
    assert len(load_snippets(path)) == MAX_SNIPPETS


def test_broken_yaml_lists_empty_and_is_backed_up_on_write(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    path.write_text("snippets: [unclosed", encoding="utf-8")

    assert load_snippets_safe(path) == []
    created = create_snippet("復旧", "本文", path)

    assert load_snippets(path) == [created]
    backups = list(tmp_path.glob("snippets.yaml.broken-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "snippets: [unclosed"


def test_invalid_entries_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "snippets": [
                    {"id": "a1", "title": "OK", "body": "b"},
                    {"id": "a1", "title": "重複", "body": "b"},
                    {"title": "idなし", "body": "b"},
                    {"id": "b2", "title": 1, "body": "b"},
                    "文字列",
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert load_snippets(path) == [{"id": "a1", "title": "OK", "body": "b"}]


def test_write_failure_raises_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(SnippetStorageError):
        create_snippet("t", "b", blocker / "snippets.yaml")


def test_concurrent_creates_are_serialized(tmp_path: Path) -> None:
    path = tmp_path / "snippets.yaml"
    threads = [
        threading.Thread(target=create_snippet, args=(f"t{i}", "b", path)) for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(load_snippets(path)) == 10


def test_default_path_uses_env(_isolated_snippets_path: Path) -> None:
    create_snippet("t", "b")
    assert _isolated_snippets_path.exists()
