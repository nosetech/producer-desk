"""レビュー承認によるリモートブランチ削除後のローカルworktree同期。

仕様: docs/basic-design.md 2-3（レビュー承認時のブランチ削除）
リモートのheadブランチ削除（github_client.delete_branch）はGitHub側の後始末に過ぎず、
Agent Runner実行用のローカルgit worktreeには影響しない。そのままだとworktreeが
削除済みブランチをチェックアウトしたまま残り、次にディスパッチされたAgent Runnerが
どのブランチで作業しているか混乱する（issue #80）。

Agent Runner用worktreeとオーケストレータ自身のソースディレクトリは同一リポジトリの
linked worktreeであり、オーケストレータ側が常時`develop`ブランチをチェックアウト
済みのため、Agent Runner用worktree側で`git checkout develop`（ブランチ名指定）を
行うとgitの「同じブランチを複数worktreeで同時チェックアウトできない」制約に必ず
抵触して失敗する。ブランチ名を保持しないdetached HEADで`origin/develop`の内容に
合わせることでこの競合を回避する（issue #88）。
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

RunFn = Callable[..., subprocess.CompletedProcess[str]]
SyncWorktreeFn = Callable[[str, str], None]

BASE_BRANCH = "develop"
BASE_REMOTE_REF = f"origin/{BASE_BRANCH}"

logger = logging.getLogger(__name__)


def sync_worktree_after_branch_delete(
    worktree_path: str, deleted_branch: str, *, run: RunFn = subprocess.run
) -> None:
    """worktreeを最新の`origin/develop`のdetached HEADへ切り替え、削除済みブランチを
    ローカルからも消す。

    `develop`ブランチ名そのものをチェックアウトすると、オーケストレータ自身の
    ソースディレクトリ（常時`develop`をチェックアウト済み）と競合して必ず失敗する
    ため、ブランチ名を保持しないdetached HEADに切り替える（issue #88）。

    `fetch`・`checkout`が失敗する場合（ネットワーク不調・未コミットの変更が残って
    いる等）は、実行中のAgent Runnerセッションを壊さないようそれ以降の処理を行わず
    ログ警告のみに留める。この処理自体の失敗は、呼び出し元（instruct.py）のレビュー
    承認成功に影響を与えない。
    """
    try:
        run(
            ["git", "-C", worktree_path, "fetch", "origin", BASE_BRANCH],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.warning(
            "worktree %s の %s fetchに失敗したため、以降の同期処理をスキップします: %s",
            worktree_path,
            BASE_REMOTE_REF,
            e,
        )
        return

    try:
        run(
            ["git", "-C", worktree_path, "checkout", "--detach", BASE_REMOTE_REF],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.warning(
            "worktree %s の %s への切り替えに失敗したため、以降の同期処理をスキップします: %s",
            worktree_path,
            BASE_REMOTE_REF,
            e,
        )
        return

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
