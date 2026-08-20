"""issueごとのAgent Runnerセッション（Claude Codeのsession-id）の永続化。

仕様: docs/basic-design.md 3-1

セッションはプロジェクト（リポジトリ）単位ではなく、issue単位で保持する。
`config/projects.yaml` にプロジェクト単位でsession_idを1つだけ保存する旧実装では、
同一プロジェクト内の複数issueが同じセッション（1本のClaude Code会話）を共有して
いたため、あるissueが判断待ちで止まっている間に別issueが同じセッションで進行す
ると、後から前者を`--resume`で再開した際に後者issueの直近の会話文脈を引きずって
しまう不具合が発生した（issue #32: 判断待ちからの再開時に、その間に処理された
別issue（#33・#38）の完了報告を返してしまった）。

`config/sessions.json`（.gitignore対象、コミットしない）に
`"{repo}#{issue_number}": "<session-id>"` の形でJSONとして保存する。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from orchestrator.config import REPO_ROOT

DEFAULT_SESSIONS_PATH = REPO_ROOT / "config" / "sessions.json"

# 環境変数 SESSIONS_PATH で読み込み先を上書きできる。運用・開発インスタンスの
# 同時起動時に、それぞれ別ファイルを使ってセッション管理を分離するために使う
# （README「リリース・日常運用」参照）。
SESSIONS_PATH_ENV = "SESSIONS_PATH"


def _resolve_sessions_path(sessions_path: Path | None) -> Path:
    if sessions_path is not None:
        return sessions_path
    return Path(os.environ.get(SESSIONS_PATH_ENV, str(DEFAULT_SESSIONS_PATH)))


def _key(repo: str, issue_number: int) -> str:
    return f"{repo}#{issue_number}"


def load_sessions(sessions_path: Path | None = None) -> dict[str, str]:
    sessions_path = _resolve_sessions_path(sessions_path)
    if not sessions_path.exists():
        return {}
    with sessions_path.open(encoding="utf-8") as f:
        return json.load(f)


def get_session_id(
    repo: str, issue_number: int, *, sessions_path: Path | None = None
) -> str | None:
    return load_sessions(sessions_path=sessions_path).get(_key(repo, issue_number))


def persist_session_id(
    repo: str,
    issue_number: int,
    session_id: str,
    *,
    sessions_path: Path | None = None,
) -> None:
    sessions_path = _resolve_sessions_path(sessions_path)
    sessions = load_sessions(sessions_path=sessions_path)
    sessions[_key(repo, issue_number)] = session_id
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    sessions_path.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
