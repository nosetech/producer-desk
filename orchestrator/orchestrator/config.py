"""config/projects.yaml の読み込み。

仕様: docs/basic-design.md 2-1（対象リポジトリ一覧の管理）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "projects.yaml"

# 環境変数 PROJECTS_CONFIG_PATH で読み込み先を上書きできる。運用インスタンスを
# 動かしたまま開発用インスタンスを並行起動する際、本番運用中の実プロジェクトを
# 対象に含めないよう、別のconfigファイル（テスト用プロジェクトを指すもの）を
# 指定するために使う（README「リリース・日常運用」参照）。
CONFIG_PATH_ENV = "PROJECTS_CONFIG_PATH"

# logs/orchestrator.log・logs/<repo>/*.log（Agent Runner個別実行ログ）双方の
# 保持日数の既定値。config/projects.yamlの`log_retention_days`未設定時に使う
# （issue #114）。
DEFAULT_LOG_RETENTION_DAYS = 7


@dataclass
class Project:
    repo: str
    worktree_path: str


def _load_yaml_data(config_path: Path | None) -> dict:
    if config_path is None:
        config_path = Path(os.environ.get(CONFIG_PATH_ENV, str(DEFAULT_CONFIG_PATH)))

    if not config_path.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {config_path}\n"
            f"{config_path.with_suffix('.yaml.example')} を参考に作成してください。"
        )

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_projects(config_path: Path | None = None) -> list[Project]:
    data = _load_yaml_data(config_path)
    return [Project(**entry) for entry in data.get("projects", [])]


def load_log_retention_days(config_path: Path | None = None) -> int:
    data = _load_yaml_data(config_path)
    return int(data.get("log_retention_days", DEFAULT_LOG_RETENTION_DAYS))
