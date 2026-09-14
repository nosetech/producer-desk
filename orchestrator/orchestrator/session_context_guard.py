"""Claude Code CLIセッションtranscriptから現在の会話文脈サイズを推定する。

仕様: docs/basic-design.md 4章「オーケストレータ側での会話量・ターン数上限による
セッションリセット（issue #189）」

issue #189で明らかになった通り、Claude Code CLI自身のauto-compaction（自動
コンテキスト圧縮）は、`execution_mode: litellm_proxy`で使う小コンテキストの
ローカルLLMには実効的に間に合わない（発火タイミングがモデルの実容量より
大幅に遅い）。オーケストレータ側でAgent Runner呼び出しのたびに会話量を
直接測定し、モデルの実容量に達する前にセッションを打ち切る判断へ使う。

測定方法はissue #189の実機調査そのもの: Claude Code CLIはセッションの
会話全体を`~/.claude/projects/<cwdをエスケープしたディレクトリ名>/
<session-id>.jsonl`にNDJSON形式で保存している。このファイルの最後の
assistantメッセージの`usage`（`input_tokens + cache_creation_input_tokens +
cache_read_input_tokens`）が、その時点で実際にモデルへ送られた文脈サイズに
最も近い。

これはClaude Code CLIの非公式な内部実装（ファイル形式・保存先パスの規則）に
依存する連携であり、CLIのアップデートで変わりうる。そのため本モジュールは
失敗時に例外を送出せず常に`None`を返し、呼び出し側（agent_runner.py）は
`None`の場合トークンベースの判定をスキップしてターン数ベースの判定へ
フォールバックする。
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def _escape_cwd(worktree_path: Path) -> str:
    # Claude Code CLIは`cwd`の絶対パスの各`/`を`-`に置き換えたディレクトリ名を
    # `~/.claude/projects/`配下に使う（先頭の`/`も`-`になる）。
    return str(worktree_path.resolve()).replace("/", "-")


def resolve_transcript_path(
    worktree_path: Path,
    session_id: str,
    *,
    claude_projects_dir: Path = DEFAULT_CLAUDE_PROJECTS_DIR,
) -> Path:
    return claude_projects_dir / _escape_cwd(worktree_path) / f"{session_id}.jsonl"


def read_latest_context_tokens(transcript_path: Path) -> int | None:
    """transcriptの最後のassistantメッセージから現在の文脈サイズを読む。

    ファイルが存在しない・壊れている等の場合はNoneを返す（呼び出し側は
    トークンベースの判定を諦め、ターン数ベースの判定にフォールバックする）。
    """
    try:
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        message = data.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        try:
            return (
                int(usage.get("input_tokens", 0) or 0)
                + int(usage.get("cache_creation_input_tokens", 0) or 0)
                + int(usage.get("cache_read_input_tokens", 0) or 0)
            )
        except (TypeError, ValueError):
            return None

    return None
