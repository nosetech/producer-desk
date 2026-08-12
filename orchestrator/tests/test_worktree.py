"""orchestrator.worktree の単体テスト。git呼び出しはフェイクに差し替える。"""

from __future__ import annotations

import subprocess

from orchestrator.worktree import sync_worktree_after_branch_delete


def _fake_run(
    *, fail_checkout: bool = False, fail_pull: bool = False, fail_branch_delete: bool = False
):
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        check = kwargs.get("check", False)

        if "checkout" in cmd and fail_checkout:
            if check:
                raise subprocess.CalledProcessError(1, cmd, stderr="checkout failed")
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="checkout failed"
            )

        if "pull" in cmd and fail_pull:
            if check:
                raise subprocess.CalledProcessError(1, cmd, stderr="pull failed")
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="pull failed")

        if "branch" in cmd and fail_branch_delete:
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="branch delete failed"
            )

        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_sync_worktree_after_branch_delete_checks_out_develop_pulls_and_deletes_local_branch() -> (
    None
):
    fake_run = _fake_run()

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "checkout", "develop"],
        ["git", "-C", "/path/to/worktree", "pull"],
        ["git", "-C", "/path/to/worktree", "branch", "-D", "feature/80-something"],
    ]


def test_sync_worktree_after_branch_delete_skips_pull_and_branch_delete_when_checkout_fails() -> (
    None
):
    fake_run = _fake_run(fail_checkout=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "checkout", "develop"],
    ]


def test_sync_worktree_after_branch_delete_deletes_local_branch_even_if_pull_fails() -> None:
    fake_run = _fake_run(fail_pull=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "checkout", "develop"],
        ["git", "-C", "/path/to/worktree", "pull"],
        ["git", "-C", "/path/to/worktree", "branch", "-D", "feature/80-something"],
    ]


def test_sync_worktree_after_branch_delete_does_not_raise_when_branch_delete_fails() -> None:
    fake_run = _fake_run(fail_branch_delete=True)

    sync_worktree_after_branch_delete("/path/to/worktree", "feature/80-something", run=fake_run)

    assert fake_run.calls == [
        ["git", "-C", "/path/to/worktree", "checkout", "develop"],
        ["git", "-C", "/path/to/worktree", "pull"],
        ["git", "-C", "/path/to/worktree", "branch", "-D", "feature/80-something"],
    ]
