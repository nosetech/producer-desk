"""issueごとの実行手段の都度上書き指定（issue #176）の永続化。

仕様: docs/basic-design.md 4章「issueコメントでの都度指示」

ダッシュボードの自由記述指示またはGitHub issueへの直接コメントで、当該issueへの
以降のディスパッチに限り実行手段をプロジェクトのデフォルトから一時的に変更できる
（`orchestrator.execution_mode`が本モジュールを使って永続化・参照する）。
`session_store.py`と同様、issue単位（`"{repo}#{issue_number}"`）で
`config/execution_overrides.json`（.gitignore対象、コミットしない）にJSONとして
保存する。プロジェクト単位ではなくissue単位にする理由もsession_store.pyと同じで、
同一プロジェクト内の他issueの都度指示に影響されないようにするため。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from orchestrator.config import REPO_ROOT

DEFAULT_EXECUTION_OVERRIDES_PATH = REPO_ROOT / "config" / "execution_overrides.json"

# 環境変数 EXECUTION_OVERRIDES_PATH で読み込み先を上書きできる（session_store.pyの
# SESSIONS_PATH_ENVと同様、運用・開発インスタンスの同時起動時に分離するため）。
EXECUTION_OVERRIDES_PATH_ENV = "EXECUTION_OVERRIDES_PATH"


def _resolve_overrides_path(overrides_path: Path | None) -> Path:
    if overrides_path is not None:
        return overrides_path
    return Path(os.environ.get(EXECUTION_OVERRIDES_PATH_ENV, str(DEFAULT_EXECUTION_OVERRIDES_PATH)))


def _key(repo: str, issue_number: int) -> str:
    return f"{repo}#{issue_number}"


def _load_overrides(overrides_path: Path | None) -> dict[str, dict]:
    overrides_path = _resolve_overrides_path(overrides_path)
    if not overrides_path.exists():
        return {}
    with overrides_path.open(encoding="utf-8") as f:
        return json.load(f)


def get_execution_override(
    repo: str, issue_number: int, *, overrides_path: Path | None = None
) -> dict | None:
    """issueに保存済みの都度上書き指定を返す（`{"execution_mode": ..., "litellm_model": ...}`）。

    上書き指定が無い場合は`None`（プロジェクトのデフォルト設定を使う）。
    """
    return _load_overrides(overrides_path).get(_key(repo, issue_number))


def persist_execution_override(
    repo: str,
    issue_number: int,
    execution_mode: str,
    litellm_model: str | None,
    *,
    overrides_path: Path | None = None,
) -> None:
    resolved_path = _resolve_overrides_path(overrides_path)
    overrides = _load_overrides(resolved_path)
    overrides[_key(repo, issue_number)] = {
        "execution_mode": execution_mode,
        "litellm_model": litellm_model,
    }
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
