"""orchestrator.config の単体テスト。

環境変数 PROJECTS_CONFIG_PATH でのconfigファイルパス上書き（README「リリース・
日常運用」、運用・開発インスタンスの同時起動対応）を検証する。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import (
    CONFIG_PATH_ENV,
    DEFAULT_LOG_RETENTION_DAYS,
    _detect_repo_root,
    load_log_retention_days,
    load_projects,
)


def test_load_projects_reads_config_path_env_var_when_arg_omitted(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "dev-projects.yaml"
    config_path.write_text(
        "projects:\n  - repo: nosetech/project-a\n    worktree_path: /tmp/project-a\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config_path))

    projects = load_projects()

    assert [p.repo for p in projects] == ["nosetech/project-a"]


def test_load_projects_explicit_arg_takes_precedence_over_env_var(
    monkeypatch, tmp_path: Path
) -> None:
    env_config_path = tmp_path / "env-projects.yaml"
    env_config_path.write_text(
        "projects:\n  - repo: nosetech/env-project\n    worktree_path: /tmp/env-project\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_PATH_ENV, str(env_config_path))

    explicit_config_path = tmp_path / "explicit-projects.yaml"
    explicit_config_path.write_text(
        "projects:\n"
        "  - repo: nosetech/explicit-project\n"
        "    worktree_path: /tmp/explicit-project\n",
        encoding="utf-8",
    )

    projects = load_projects(config_path=explicit_config_path)

    assert [p.repo for p in projects] == ["nosetech/explicit-project"]


def test_load_log_retention_days_returns_default_when_key_absent(tmp_path: Path) -> None:
    config_path = tmp_path / "projects.yaml"
    config_path.write_text(
        "projects:\n  - repo: nosetech/project-a\n    worktree_path: /tmp/project-a\n",
        encoding="utf-8",
    )

    assert load_log_retention_days(config_path=config_path) == DEFAULT_LOG_RETENTION_DAYS


def test_load_log_retention_days_reads_custom_value(tmp_path: Path) -> None:
    config_path = tmp_path / "projects.yaml"
    config_path.write_text(
        "projects: []\nlog_retention_days: 14\n",
        encoding="utf-8",
    )

    assert load_log_retention_days(config_path=config_path) == 14


def test_load_log_retention_days_clamps_non_positive_value_to_one(tmp_path: Path) -> None:
    config_path = tmp_path / "projects.yaml"
    config_path.write_text(
        "projects: []\nlog_retention_days: 0\n",
        encoding="utf-8",
    )

    assert load_log_retention_days(config_path=config_path) == 1


def test_detect_repo_root_uses_file_ancestor_for_editable_install(tmp_path: Path) -> None:
    repo_root = tmp_path / "producer-desk"
    (repo_root / "orchestrator" / "orchestrator").mkdir(parents=True)
    (repo_root / "orchestrator" / "pyproject.toml").write_text("", encoding="utf-8")
    module_file = repo_root / "orchestrator" / "orchestrator" / "config.py"

    assert _detect_repo_root(str(module_file)) == repo_root


def test_detect_repo_root_falls_back_to_cwd_for_wheel_install(monkeypatch, tmp_path: Path) -> None:
    site_packages = tmp_path / "venv" / "lib" / "python3.11" / "site-packages"
    (site_packages / "orchestrator").mkdir(parents=True)
    module_file = site_packages / "orchestrator" / "config.py"
    cwd = tmp_path / "producer-desk-0.1.0"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    assert _detect_repo_root(str(module_file)) == cwd
