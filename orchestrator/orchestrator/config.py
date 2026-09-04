"""config/projects.yaml の読み込み。

仕様: docs/basic-design.md 2-1（対象リポジトリ一覧の管理）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


def _detect_repo_root(module_file: str = __file__) -> Path:
    """`config/`・`logs/`等の既定の親ディレクトリを検出する。

    editable install（`pip install -e .`、開発時のgit clone運用）では、本ファイル
    （`orchestrator/orchestrator/config.py`）はソースツリー上に存在し続けるため、
    2階層上（`orchestrator/pyproject.toml`が存在するディレクトリの親）がリポジトリ
    ルートになる。一方、`pip install <wheel>`でのインストール（配布パッケージ、
    issue #110）ではファイルが`site-packages/orchestrator/`直下にフラットに配置
    され、この逆算が別ディレクトリを指してしまう。`orchestrator/pyproject.toml`の
    有無でどちらのインストール形態かを判定し、wheelインストール時はカレント
    ディレクトリ（配布物のルートディレクトリで起動する前提。dist/bin/start.sh参照）
    を採用する。
    """
    candidate = Path(module_file).resolve().parents[2]
    if (candidate / "orchestrator" / "pyproject.toml").exists():
        return candidate
    return Path.cwd()


REPO_ROOT = _detect_repo_root()
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

# 自走タスク本体の実行手段（issue #148・#174・#176、docs/basic-design.md 4章）。
# (A) Claude Code CLI直利用＋サブスクリプション（既定）と、
# (B) LiteLLM Proxy経由の他モデル・ローカルLLM＋従量課金のいずれか。
EXECUTION_MODE_CLAUDE_CODE = "claude_code"
EXECUTION_MODE_LITELLM_PROXY = "litellm_proxy"
VALID_EXECUTION_MODES = frozenset({EXECUTION_MODE_CLAUDE_CODE, EXECUTION_MODE_LITELLM_PROXY})


@dataclass
class Project:
    repo: str
    worktree_path: str
    # (B) LiteLLM Proxy経由選択時は、LiteLLM Proxy側のconfig.yaml（model_list）で
    # 定義したモデルエイリアス名を保持する（`claude -p --model <litellm_model>`として
    # 渡す。orchestrator/orchestrator/agent_runner.py参照）。
    execution_mode: str = EXECUTION_MODE_CLAUDE_CODE
    litellm_model: str | None = None

    def __post_init__(self) -> None:
        validate_execution_settings(self.execution_mode, self.litellm_model, context=self.repo)


def validate_execution_settings(
    execution_mode: str, litellm_model: str | None, *, context: str
) -> None:
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(
            f"{context}: execution_modeは{sorted(VALID_EXECUTION_MODES)}のいずれかである"
            f"必要があります（実際の値: {execution_mode!r}）。"
        )
    if execution_mode == EXECUTION_MODE_LITELLM_PROXY and not litellm_model:
        raise ValueError(
            f"{context}: execution_modeが{EXECUTION_MODE_LITELLM_PROXY!r}の場合、"
            "litellm_modelの指定が必須です。"
        )


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
    value = int(data.get("log_retention_days", DEFAULT_LOG_RETENTION_DAYS))
    # 0以下だと、書き込み直後のログファイルもTimedRotatingFileHandlerの
    # backupCount管理・cleanup_old_agent_logs（agent_runner.py）のmtime判定で
    # 即座に削除されうるため、最低1日は保持する（issue #114）。
    return max(1, value)


def _resolve_config_path(config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path
    return Path(os.environ.get(CONFIG_PATH_ENV, str(DEFAULT_CONFIG_PATH)))


# issue #176: ダッシュボードのプロジェクト設定UI（issue #175、本関数に依存）から
# 実行手段のデフォルト設定を更新するための永続化API。「GitHub Issues/Projectsが
# 正のデータストア」という確定済み設計判断（CLAUDE.md）はissueそのものの状態に
# 関するものであり、プロジェクト単位の運用設定は元々config/projects.yaml
# （オーケストレータのみが読む設定ファイル）で管理している（2-1章）ため、実行手段の
# デフォルト設定もこのファイルに追加する形で一貫させる。
def update_project_execution_settings(
    repo: str,
    execution_mode: str,
    litellm_model: str | None,
    *,
    config_path: Path | None = None,
) -> Project:
    """`config/projects.yaml`の対象プロジェクトエントリの実行手段設定を更新する。

    既存のYAML全体（他プロジェクトのエントリ・`log_retention_days`等）は
    `yaml.safe_load`で読み込んだdictをそのまま使い、対象エントリのみ書き換えて
    `yaml.safe_dump`で書き戻す（コメントは保持されないが、実データである
    `config/projects.yaml`自体は.gitignore対象でコメント運用を前提としていない。
    コメント付きの`.yaml.example`は本関数の対象外）。
    """
    validate_execution_settings(execution_mode, litellm_model, context=repo)
    if execution_mode != EXECUTION_MODE_LITELLM_PROXY:
        # claude_code時にlitellm_modelが誤って（クライアントの実装ミス等で）
        # 送られてきても無視し、YAMLに不要なフィールドを残さない。
        litellm_model = None

    resolved_path = _resolve_config_path(config_path)
    data = _load_yaml_data(resolved_path)
    entries = data.get("projects", [])

    for entry in entries:
        if entry.get("repo") == repo:
            entry["execution_mode"] = execution_mode
            if litellm_model is not None:
                entry["litellm_model"] = litellm_model
            else:
                entry.pop("litellm_model", None)
            break
    else:
        raise ValueError(f"config/projects.yamlに未登録のリポジトリです: {repo}")

    resolved_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return Project(
        repo=repo,
        worktree_path=entry["worktree_path"],
        execution_mode=execution_mode,
        litellm_model=litellm_model,
    )
