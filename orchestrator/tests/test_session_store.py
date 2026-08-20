"""orchestrator.session_store の単体テスト。

docs/basic-design.md 3-1（セッションはissue単位で`config/sessions.json`に
保存する）を検証する。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.session_store import (
    SESSIONS_PATH_ENV,
    get_session_id,
    load_sessions,
    persist_session_id,
)


def test_get_session_id_returns_none_when_file_does_not_exist(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    assert get_session_id("nosetech/project-a", 12, sessions_path=sessions_path) is None


def test_persist_session_id_creates_file_and_is_readable_back(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_id("nosetech/project-a", 12, "abc-123", sessions_path=sessions_path)

    assert get_session_id("nosetech/project-a", 12, sessions_path=sessions_path) == "abc-123"


def test_persist_session_id_keys_by_repo_and_issue_number_independently(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_id("nosetech/project-a", 12, "session-for-12", sessions_path=sessions_path)
    persist_session_id("nosetech/project-a", 13, "session-for-13", sessions_path=sessions_path)
    persist_session_id("nosetech/project-b", 12, "session-for-b-12", sessions_path=sessions_path)

    assert get_session_id("nosetech/project-a", 12, sessions_path=sessions_path) == "session-for-12"
    assert get_session_id("nosetech/project-a", 13, sessions_path=sessions_path) == "session-for-13"
    assert (
        get_session_id("nosetech/project-b", 12, sessions_path=sessions_path) == "session-for-b-12"
    )


def test_persist_session_id_overwrites_existing_value_for_same_key(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_id("nosetech/project-a", 12, "old-session", sessions_path=sessions_path)
    persist_session_id("nosetech/project-a", 12, "new-session", sessions_path=sessions_path)

    assert get_session_id("nosetech/project-a", 12, sessions_path=sessions_path) == "new-session"


def test_persist_session_id_preserves_other_keys(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_id("nosetech/project-a", 12, "session-for-12", sessions_path=sessions_path)
    persist_session_id("nosetech/project-a", 13, "session-for-13", sessions_path=sessions_path)

    sessions = load_sessions(sessions_path=sessions_path)
    assert sessions == {
        "nosetech/project-a#12": "session-for-12",
        "nosetech/project-a#13": "session-for-13",
    }


def test_load_sessions_returns_empty_dict_when_file_does_not_exist(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    assert load_sessions(sessions_path=sessions_path) == {}


def test_persist_session_id_reads_sessions_path_env_var_when_arg_omitted(
    monkeypatch, tmp_path: Path
) -> None:
    sessions_path = tmp_path / "dev-sessions.json"
    monkeypatch.setenv(SESSIONS_PATH_ENV, str(sessions_path))

    persist_session_id("nosetech/project-a", 12, "abc-123")

    assert get_session_id("nosetech/project-a", 12) == "abc-123"
    assert sessions_path.exists()


def test_persist_session_id_explicit_arg_takes_precedence_over_env_var(
    monkeypatch, tmp_path: Path
) -> None:
    env_sessions_path = tmp_path / "env-sessions.json"
    monkeypatch.setenv(SESSIONS_PATH_ENV, str(env_sessions_path))

    explicit_sessions_path = tmp_path / "explicit-sessions.json"
    persist_session_id("nosetech/project-a", 12, "abc-123", sessions_path=explicit_sessions_path)

    assert not env_sessions_path.exists()
    assert get_session_id("nosetech/project-a", 12, sessions_path=explicit_sessions_path) == (
        "abc-123"
    )
