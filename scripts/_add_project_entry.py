#!/usr/bin/env python3
"""config/projects.yaml へ repo/worktree_path エントリを追記する。

scripts/add_project.sh から呼び出される内部ヘルパー。config/projects.yaml の
実際のスキーマ（orchestrator/orchestrator/config.py の Project）は repo・
worktree_path の2フィールドのみの単純なリストのため、PyYAML等の追加依存を
持ち込まず標準ライブラリのみでテキストとして直接追記する（配布パッケージ利用者に
orchestrator側の`pip install -e ".[dev]"`相当を要求しないため。issue #128）。
"""

from __future__ import annotations

import re
import sys

REPO_LINE_RE = re.compile(r"^\s*-\s*repo:\s*(\S+)\s*$")
WORKTREE_LINE_RE = re.compile(r"^\s*worktree_path:\s*\S+\s*$")


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"使い方: {sys.argv[0]} <config-path> <owner/repo> <worktree-path>",
            file=sys.stderr,
        )
        return 1

    config_path, repo, worktree_path = sys.argv[1:4]

    try:
        with open(config_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = ["projects:\n"]

    for line in lines:
        m = REPO_LINE_RE.match(line)
        if m and m.group(1) == repo:
            print(
                f"エラー: {repo} は既に {config_path} に登録済みです（重複登録はできません）",
                file=sys.stderr,
            )
            return 1

    insert_at = None
    for i, line in enumerate(lines):
        if WORKTREE_LINE_RE.match(line):
            insert_at = i + 1

    if insert_at is None:
        for i, line in enumerate(lines):
            if line.strip() == "projects:":
                insert_at = i + 1
                break

    if insert_at is None:
        lines.append("projects:\n")
        insert_at = len(lines)

    new_entry = f"  - repo: {repo}\n    worktree_path: {worktree_path}\n"
    lines.insert(insert_at, new_entry)

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"config/projects.yaml に追記しました: repo={repo}, worktree_path={worktree_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
