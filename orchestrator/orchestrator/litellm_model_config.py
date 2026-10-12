"""config/litellm_config.yamlのmodel_listから、モデルごとのセッションガード設定を読む。

仕様: docs/basic-design.md 4章「オーケストレータ側での会話量・ターン数上限による
セッションリセット（issue #189）」

`max_session_tokens`/`max_session_turns`は「そのモデルがどれだけの会話量を
扱えるか」という関心事であり、`config/litellm_config.yaml`の`model_list[].
litellm_params.num_ctx`と同じ性質の設定値である。プロジェクト単位の
`config/projects.yaml`ではなく、num_ctxと同じ`config/litellm_config.yaml`の
`model_list[].model_info`に定義することで、両者を1箇所で一貫して管理できる
（`model_info.repo`と同様、`model_info`はLiteLLM自体には転送されないオーケス
トレータ側の付加メタデータ）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from orchestrator.config import REPO_ROOT

DEFAULT_LITELLM_CONFIG_PATH = REPO_ROOT / "config" / "litellm_config.yaml"

# 環境変数 LITELLM_CONFIG_PATH で読み込み先を上書きできる（config/projects.yaml
# の PROJECTS_CONFIG_PATH と同様、運用・開発インスタンスの同時起動時に分離する
# ための仕組み）。
LITELLM_CONFIG_PATH_ENV = "LITELLM_CONFIG_PATH"


@dataclass
class SessionGuardSettings:
    max_session_tokens: int | None
    max_session_turns: int | None


_EMPTY = SessionGuardSettings(max_session_tokens=None, max_session_turns=None)


def _resolve_config_path(config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path
    return Path(os.environ.get(LITELLM_CONFIG_PATH_ENV, str(DEFAULT_LITELLM_CONFIG_PATH)))


def resolve_session_guard_settings(
    litellm_model: str | None, *, config_path: Path | None = None
) -> SessionGuardSettings:
    """`model_name == litellm_model`のmodel_listエントリからmodel_infoの値を読む。

    設定ファイルが存在しない・該当エントリが見つからない・値が未設定の場合は
    いずれも無制限（None）として扱う（LiteLLM Proxy自体の起動可否は別途
    `litellm_proxy.is_healthy`で確認しており、本関数はセッションガードの追加
    情報を補うだけの役割のため、ここで例外を送出して自走タスクの進行を止め
    ない）。`litellm_model`がNone（execution_mode: claude_code等）の場合も
    同様に無制限として扱う。
    """
    if litellm_model is None:
        return _EMPTY

    config_path = _resolve_config_path(config_path)
    if not config_path.exists():
        return _EMPTY

    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    for entry in data.get("model_list") or []:
        if not isinstance(entry, dict) or entry.get("model_name") != litellm_model:
            continue
        model_info = entry.get("model_info") or {}
        return SessionGuardSettings(
            max_session_tokens=model_info.get("max_session_tokens"),
            max_session_turns=model_info.get("max_session_turns"),
        )

    return _EMPTY
