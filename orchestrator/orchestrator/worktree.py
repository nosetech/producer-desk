"""レビュー承認によるリモートブランチ削除後のローカルworktree同期。

仕様: docs/basic-design.md 2-3（レビュー承認時のブランチ削除）
リモートのheadブランチ削除（github_client.delete_branch）はGitHub側の後始末に過ぎず、
Agent Runner実行用のローカルgit worktreeには影響しない。そのままだとworktreeが
削除済みブランチをチェックアウトしたまま残り、次にディスパッチされたAgent Runnerが
どのブランチで作業しているか混乱する（issue #80）。
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

RunFn = Callable[..., subprocess.CompletedProcess[str]]
SyncWorktreeFn = Callable[[str, str], None]

BASE_BRANCH = "develop"

logger = logging.getLogger(__name__)


def sync_worktree_after_branch_delete(
    worktree_path: str, deleted_branch: str, *, run: RunFn = subprocess.run
) -> None:
    """worktreeを`develop`へ切り替え・最新化し、削除済みブランチをローカルからも消す。

    `checkout`が失敗する場合（未コミットの変更が残っている等）は、実行中のAgent Runner
    セッションを壊さないようそれ以降の`pull`・ローカルブランチ削除を行わずログ警告のみ
    に留める。この処理自体の失敗は、呼び出し元（instruct.py）のレビュー承認成功に
    影響を与えない。
    """
    try:
        run(
            ["git", "-C", worktree_path, "checkout", BASE_BRANCH],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.warning(
            "worktree %s の %s への切り替えに失敗したため、以降の同期処理をスキップします: %s",
            worktree_path,
            BASE_BRANCH,
            e,
        )
        return

    try:
        run(
            ["git", "-C", worktree_path, "pull"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.warning("worktree %s の pull に失敗しました: %s", worktree_path, e)

    result = run(
        ["git", "-C", worktree_path, "branch", "-D", deleted_branch],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "worktree %s のローカルブランチ %s 削除に失敗しました: %s",
            worktree_path,
            deleted_branch,
            result.stderr,
        )
