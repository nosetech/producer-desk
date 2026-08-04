"""config/projects.yaml へのsession_id書き戻し。

仕様: docs/basic-design.md 3-1
「初回ディスパッチ時はオーケストレータがuuid.uuid4()を生成し--session-idで明示的に
指定してセッションを新規作成する。生成したIDをconfig/projects.yamlに書き戻し、
以降の指示では--resume <session-id>で再開する。」

PyYAMLでの全体再シリアライズはユーザーが記載したコメント等を壊すため、対象repoの
ブロック内にある `session_id:` 行だけを正規表現で置換するテキスト差分更新を行う。
"""

from __future__ import annotations

import re
from pathlib import Path

from orchestrator.config import DEFAULT_CONFIG_PATH

_REPO_LINE = re.compile(r"^\s*-\s*repo:\s*(?P<value>\S+)\s*$")
_NEXT_ENTRY_LINE = re.compile(r"^\s*-\s*repo:\s*")
_SESSION_ID_LINE = re.compile(
    r"^(?P<indent>\s*session_id:\s*)(?P<value>[^#\r\n]*?)(?P<trailer>\s*#.*)?$"
)


def update_session_id(yaml_text: str, repo: str, session_id: str) -> str:
    """`yaml_text` 内の該当repoブロックの `session_id` 値だけを書き換えた新しいテキストを返す。"""
    lines = yaml_text.splitlines(keepends=True)

    block_start = None
    for i, line in enumerate(lines):
        m = _REPO_LINE.match(line.rstrip("\n"))
        if m and m.group("value").strip("\"'") == repo:
            block_start = i
            break

    if block_start is None:
        raise ValueError(f"config内にrepoが見つかりません: {repo}")

    block_end = len(lines)
    for j in range(block_start + 1, len(lines)):
        if _NEXT_ENTRY_LINE.match(lines[j]):
            block_end = j
            break

    for k in range(block_start, block_end):
        m = _SESSION_ID_LINE.match(lines[k].rstrip("\n"))
        if m:
            newline = "\n" if lines[k].endswith("\n") else ""
            trailer = m.group("trailer") or ""
            lines[k] = f'{m.group("indent")}"{session_id}"{trailer}{newline}'
            return "".join(lines)

    raise ValueError(f"repo={repo} のブロックにsession_idキーが見つかりません")


def persist_session_id(
    repo: str, session_id: str, *, config_path: Path = DEFAULT_CONFIG_PATH
) -> None:
    text = config_path.read_text(encoding="utf-8")
    updated = update_session_id(text, repo, session_id)
    config_path.write_text(updated, encoding="utf-8")
