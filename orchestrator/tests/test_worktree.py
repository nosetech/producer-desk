"""orchestrator.worktree の単体テスト。git呼び出しはフェイクに差し替える。"""

from __future__ import annotations

import subprocess

from orchestrator.worktree import sync_worktree_after_branch_delete


def _fake_run(
    *, fail_fetch: bool = False, fail_checkout: bool = False, fail_branch_delete: bool = False
):
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        check = kwargs.get("check", False)

        if "fetch" in cmd and fail_fetch:
            if check:
                raise subprocess.CalledProcessError(1, cmd, stderr="fetch failed")
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="fetch failed")

        if "checkout" in cmd and fail_checkout:
            if check:
                raise subprocess.CalledProcessError(1, cmd, stderr="checkout failed")
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="checkout failed"
            )

        if "branch" in cmd and fail_branch_delete:
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="branch delete failed"
            )

        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_sync_worktree_after_branch_delete_fetches_and_checks_out_detached() -> None:
    fake_run = _fake_run()

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "fetch", "origin", "develop"],
        ["git", "-C", "/path/to/worktree", "checkout", "--detach", "origin/develop"],
        ["git", "-C", "/path/to/worktree", "branch", "-D", "feature/80-something"],
    ]


def test_sync_worktree_after_branch_delete_skips_checkout_and_branch_delete_when_fetch_fails() -> (
    None
):
    """fetch失敗時はcheckout・ローカルブランチ削除を行わない（issue #88）。"""
    fake_run = _fake_run(fail_fetch=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "fetch", "origin", "develop"],
    ]


def test_sync_worktree_after_branch_delete_skips_branch_delete_when_checkout_fails() -> None:
    """checkout --detach失敗時はローカルブランチ削除を行わない（issue #88）。"""
    fake_run = _fake_run(fail_checkout=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "fetch", "origin", "develop"],
        ["git", "-C", "/path/to/worktree", "checkout", "--detach", "origin/develop"],
    ]


def test_sync_worktree_after_branch_delete_does_not_raise_when_branch_delete_fails() -> None:
    fake_run = _fake_run(fail_branch_delete=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "fetch", "origin", "develop"],
        ["git", "-C", "/path/to/worktree", "checkout", "--detach", "origin/develop"],
        ["git", "-C", "/path/to/worktree", "branch", "-D", "feature/80-something"],
    ]


def _run_git(args: list[str], *, cwd: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_sync_worktree_after_branch_delete_succeeds_even_when_develop_is_checked_out_elsewhere(
    tmp_path,
) -> None:
    """develop が別のlinked worktree（オーケストレータ自身のソース）で既にチェックアウト
    済みでも、同期処理は失敗しない（issue #88の実際の再現ケース）。

    `git checkout develop`（ブランチ名指定）だと、gitの「同じブランチを複数worktreeで
    同時チェックアウトできない」制約に抵触して常に失敗していた。detached HEADへの
    切り替えに変更したことで、develop が他のworktreeで使用中でも成功することを
    実際のgitコマンドで検証する。
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "develop", str(origin)], check=True)

    main_worktree = tmp_path / "main"
    subprocess.run(["git", "clone", str(origin), str(main_worktree)], check=True)
    _run_git(["config", "user.email", "test@example.com"], cwd=str(main_worktree))
    _run_git(["config", "user.name", "Test"], cwd=str(main_worktree))
    _run_git(["commit", "--allow-empty", "-m", "initial"], cwd=str(main_worktree))
    _run_git(["push", "-u", "origin", "develop"], cwd=str(main_worktree))
    develop_commit = _run_git(["rev-parse", "develop"], cwd=str(main_worktree))

    agent_worktree = tmp_path / "agent"
    _run_git(
        ["worktree", "add", "-b", "feature/80-something", str(agent_worktree), "develop"],
        cwd=str(main_worktree),
    )

    # main_worktree は develop をチェックアウトしたまま（オーケストレータ自身のソース
    # ディレクトリに相当）。この状態でagent_worktree側の同期処理を実行する。
    assert _run_git(["branch", "--show-current"], cwd=str(main_worktree)) == "develop"

    sync_worktree_after_branch_delete(str(agent_worktree), "feature/80-something")

    # detached HEADでdevelopの最新コミットを指しており、featureブランチはローカルから
    # 削除されている。
    assert _run_git(["branch", "--show-current"], cwd=str(agent_worktree)) == ""
    assert _run_git(["rev-parse", "HEAD"], cwd=str(agent_worktree)) == develop_commit
    assert _run_git(["branch", "--list", "feature/80-something"], cwd=str(agent_worktree)) == ""
    # main_worktree側のdevelopチェックアウトは影響を受けない。
    assert _run_git(["branch", "--show-current"], cwd=str(main_worktree)) == "develop"
