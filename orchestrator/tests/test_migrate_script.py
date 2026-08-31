"""dist/scripts/migrate.sh の統合テスト。

配布パッケージのバージョンアップ時に、旧展開先ディレクトリのユーザー固有
状態ファイル（config/projects.yaml・config/usage.db・config/sessions.json・
.env・logs/）を新展開先ディレクトリへ引き継ぐマイグレーションツール（issue #155）。
純粋なbashスクリプトのため専用のテストフレームワークは持ち込まず、
subprocessで実際に実行してファイルシステム上の結果を検証する。
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

MIGRATE_SCRIPT = Path(__file__).resolve().parents[2] / "dist" / "scripts" / "migrate.sh"


def _make_old_root(tmp_path: Path) -> Path:
    old_root = tmp_path / "old-producer-desk"
    (old_root / "config").mkdir(parents=True)
    (old_root / "config" / "projects.yaml").write_text(
        "projects:\n  - repo: nosetech/project-a\n    worktree_path: /tmp/project-a\n",
        encoding="utf-8",
    )
    (old_root / "config" / "sessions.json").write_text(
        '{"nosetech/project-a#1": "session-abc"}', encoding="utf-8"
    )
    (old_root / ".env").write_text(
        "SLACK_WEBHOOK_URL=https://hooks.slack.com/x\n", encoding="utf-8"
    )

    db_path = old_root / "config" / "usage.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, repo TEXT)")
        conn.execute("INSERT INTO usage_records (repo) VALUES ('nosetech/project-a')")
        # dist/scripts/migrate.shのEXPECTED_USAGE_DB_SCHEMA_VERSION
        # （orchestrator/orchestrator/usage_store.pyのSCHEMA_VERSIONと同じ値）と
        # 一致させる。
        conn.execute("PRAGMA user_version = 2")

    logs_dir = old_root / "logs" / "nosetech-project-a"
    logs_dir.mkdir(parents=True)
    (logs_dir / "run.log").write_text("dummy\n", encoding="utf-8")

    return old_root


def _make_new_root(tmp_path: Path) -> Path:
    new_root = tmp_path / "new-producer-desk"
    (new_root / "scripts").mkdir(parents=True)
    (new_root / "config").mkdir(parents=True)
    shutil.copy2(MIGRATE_SCRIPT, new_root / "scripts" / "migrate.sh")
    (new_root / "scripts" / "migrate.sh").chmod(0o755)
    return new_root


def _run_migrate(new_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(new_root / "scripts" / "migrate.sh"), *args],
        capture_output=True,
        text=True,
    )


def test_migrate_copies_config_and_env_but_not_logs_by_default(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(old_root))

    assert result.returncode == 0, result.stderr
    assert (new_root / "config" / "projects.yaml").read_text(encoding="utf-8") == (
        old_root / "config" / "projects.yaml"
    ).read_text(encoding="utf-8")
    assert (new_root / "config" / "sessions.json").exists()
    assert (new_root / ".env").exists()
    assert (new_root / "config" / "usage.db").exists()
    assert not (new_root / "logs").exists()


def test_migrate_with_logs_flag_copies_logs(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(old_root), "--with-logs")

    assert result.returncode == 0, result.stderr
    assert (new_root / "logs" / "nosetech-project-a" / "run.log").exists()


def test_migrate_skips_existing_files_without_force(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    new_root = _make_new_root(tmp_path)
    (new_root / "config" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")

    result = _run_migrate(new_root, str(old_root))

    assert result.returncode == 0, result.stderr
    assert (new_root / "config" / "projects.yaml").read_text(encoding="utf-8") == "projects: []\n"


def test_migrate_force_backs_up_existing_file_before_overwrite(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    new_root = _make_new_root(tmp_path)
    (new_root / "config" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")

    result = _run_migrate(new_root, str(old_root), "--force")

    assert result.returncode == 0, result.stderr
    assert (new_root / "config" / "projects.yaml").read_text(encoding="utf-8") != "projects: []\n"
    backups = list((new_root / "config").glob("projects.yaml.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "projects: []\n"


def test_migrate_rejects_invalid_sessions_json(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    (old_root / "config" / "sessions.json").write_text("{not valid json", encoding="utf-8")
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(old_root))

    assert result.returncode != 0
    assert not (new_root / "config" / "sessions.json").exists()


def test_migrate_aborts_on_incompatible_usage_db_schema_version(tmp_path: Path) -> None:
    old_root = _make_old_root(tmp_path)
    with sqlite3.connect(old_root / "config" / "usage.db") as conn:
        conn.execute("PRAGMA user_version = 999")
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(old_root))

    assert result.returncode != 0
    assert not (new_root / "config" / "usage.db").exists()
    # usage.dbより前段の項目（projects.yaml等）は失敗と無関係に移行済みであること
    assert (new_root / "config" / "projects.yaml").exists()


def test_migrate_rejects_same_source_and_destination(tmp_path: Path) -> None:
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(new_root))

    assert result.returncode != 0


@pytest.mark.parametrize(
    "missing", ["config/projects.yaml", "config/sessions.json", ".env", "config/usage.db"]
)
def test_migrate_skips_files_missing_from_old_root(tmp_path: Path, missing: str) -> None:
    old_root = _make_old_root(tmp_path)
    (old_root / missing).unlink()
    new_root = _make_new_root(tmp_path)

    result = _run_migrate(new_root, str(old_root))

    assert result.returncode == 0, result.stderr
    assert not (new_root / missing).exists()
