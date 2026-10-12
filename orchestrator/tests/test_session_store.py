"""orchestrator.session_store の単体テスト。

docs/basic-design.md 3-1（セッションはissue単位で`config/sessions.json`に
保存する）・issue #189（`turn_count`を併せて保持する）を検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.session_store import (
    SESSIONS_PATH_ENV,
    SessionState,
    clear_session_state,
    get_session_state,
    persist_session_state,
)


def test_get_session_state_returns_none_when_file_does_not_exist(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) is None


def test_persist_session_state_creates_file_and_is_readable_back(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_state(
        "nosetech/project-a", 12, SessionState("abc-123", 1), sessions_path=sessions_path
    )

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) == SessionState(
        "abc-123", 1
    )


def test_persist_session_state_keys_by_repo_and_issue_number_independently(
    tmp_path: Path,
) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_state(
        "nosetech/project-a", 12, SessionState("session-for-12", 1), sessions_path=sessions_path
    )
    persist_session_state(
        "nosetech/project-a", 13, SessionState("session-for-13", 1), sessions_path=sessions_path
    )
    persist_session_state(
        "nosetech/project-b", 12, SessionState("session-for-b-12", 1), sessions_path=sessions_path
    )

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) == SessionState(
        "session-for-12", 1
    )
    assert get_session_state("nosetech/project-a", 13, sessions_path=sessions_path) == SessionState(
        "session-for-13", 1
    )
    assert get_session_state("nosetech/project-b", 12, sessions_path=sessions_path) == SessionState(
        "session-for-b-12", 1
    )


def test_persist_session_state_overwrites_existing_value_for_same_key(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_state(
        "nosetech/project-a", 12, SessionState("old-session", 1), sessions_path=sessions_path
    )
    persist_session_state(
        "nosetech/project-a", 12, SessionState("old-session", 2), sessions_path=sessions_path
    )

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) == SessionState(
        "old-session", 2
    )


def test_persist_session_state_preserves_other_keys(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    persist_session_state(
        "nosetech/project-a", 12, SessionState("session-for-12", 1), sessions_path=sessions_path
    )
    persist_session_state(
        "nosetech/project-a", 13, SessionState("session-for-13", 1), sessions_path=sessions_path
    )

    with sessions_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    assert raw == {
        "nosetech/project-a#12": {"session_id": "session-for-12", "turn_count": 1},
        "nosetech/project-a#13": {"session_id": "session-for-13", "turn_count": 1},
    }


def test_get_session_state_reads_legacy_plain_string_format(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"
    sessions_path.write_text(
        json.dumps({"nosetech/project-a#12": "legacy-session-id"}), encoding="utf-8"
    )

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) == SessionState(
        "legacy-session-id", 0
    )


def test_clear_session_state_removes_only_target_key(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"
    persist_session_state(
        "nosetech/project-a", 12, SessionState("session-for-12", 3), sessions_path=sessions_path
    )
    persist_session_state(
        "nosetech/project-a", 13, SessionState("session-for-13", 1), sessions_path=sessions_path
    )

    clear_session_state("nosetech/project-a", 12, sessions_path=sessions_path)

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) is None
    assert get_session_state("nosetech/project-a", 13, sessions_path=sessions_path) == SessionState(
        "session-for-13", 1
    )


def test_clear_session_state_is_a_noop_when_key_does_not_exist(tmp_path: Path) -> None:
    sessions_path = tmp_path / "sessions.json"

    clear_session_state("nosetech/project-a", 12, sessions_path=sessions_path)

    assert get_session_state("nosetech/project-a", 12, sessions_path=sessions_path) is None


def test_persist_session_state_reads_sessions_path_env_var_when_arg_omitted(
    monkeypatch, tmp_path: Path
) -> None:
    sessions_path = tmp_path / "dev-sessions.json"
    monkeypatch.setenv(SESSIONS_PATH_ENV, str(sessions_path))

    persist_session_state("nosetech/project-a", 12, SessionState("abc-123", 1))

    assert get_session_state("nosetech/project-a", 12) == SessionState("abc-123", 1)
    assert sessions_path.exists()


def test_persist_session_state_explicit_arg_takes_precedence_over_env_var(
    monkeypatch, tmp_path: Path
) -> None:
    env_sessions_path = tmp_path / "env-sessions.json"
    monkeypatch.setenv(SESSIONS_PATH_ENV, str(env_sessions_path))

    explicit_sessions_path = tmp_path / "explicit-sessions.json"
    persist_session_state(
        "nosetech/project-a", 12, SessionState("abc-123", 1), sessions_path=explicit_sessions_path
    )

    assert not env_sessions_path.exists()
    assert get_session_state(
        "nosetech/project-a", 12, sessions_path=explicit_sessions_path
    ) == SessionState("abc-123", 1)
