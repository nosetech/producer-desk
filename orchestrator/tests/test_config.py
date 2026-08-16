"""orchestrator.config の単体テスト。

環境変数 PROJECTS_CONFIG_PATH でのconfigファイルパス上書き（README「リリース・
日常運用」、運用・開発インスタンスの同時起動対応）を検証する。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import CONFIG_PATH_ENV, load_projects


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
