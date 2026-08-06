"""config/projects.yaml の読み込み。

仕様: docs/basic-design.md 2-1（対象リポジトリ一覧の管理）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "projects.yaml"


@dataclass
class Project:
    repo: str
    worktree_path: str


def load_projects(config_path: Path = DEFAULT_CONFIG_PATH) -> list[Project]:
    if not config_path.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {config_path}\n"
            f"{config_path.with_suffix('.yaml.example')} を参考に作成してください。"
        )

    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return [Project(**entry) for entry in data.get("projects", [])]
