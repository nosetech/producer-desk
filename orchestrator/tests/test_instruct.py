"""orchestrator.instruct の単体テスト。

docs/basic-design.md 2-3（指示出しAPI）・5-3（内部処理フロー）の仕様を検証する。
gh呼び出し・ディスパッチキューはフェイクに差し替える。
"""

from __future__ import annotations

import subprocess
import threading

import pytest

from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.instruct import (
    APPROVE_DEFAULT_MESSAGE,
    ReviewMergeError,
    handle_create_issue,
    handle_instruct,
)
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)


class FakeLabels:
    def __init__(self, initial: set[str]) -> None:
        self.labels = set(initial)

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        return set(self.labels)

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels.add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels.discard(label)


class FakeComments:
    def __init__(self) -> None:
        self.posted: list[tuple[str, int, str]] = []

    def post_comment(self, repo: str, issue_number: int, body: str) -> None:
        self.posted.append((repo, issue_number, body))


def _synchronous_dispatch_queue() -> tuple[DispatchQueue, list[tuple[str, int, str]]]:
    calls: list[tuple[str, int, str]] = []

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        calls.append((repo, issue_number, message))

    return DispatchQueue(dispatch_fn=dispatch_fn), calls


def _wait_for(calls: list, count: int, timeout: float = 2.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(calls) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"expected {count} dispatch calls, got {len(calls)}")


def test_handle_instruct_approve_uses_default_message_and_dispatches() -> None:
    labels = FakeLabels({STATUS_NEEDS_HUMAN_DECISION})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.comment == APPROVE_DEFAULT_MESSAGE
    assert result.label == STATUS_IN_PROGRESS
    assert result.dispatched is True
    assert comments.posted == [("nosetech/project-a", 1, APPROVE_DEFAULT_MESSAGE)]
    assert labels.labels == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 1, APPROVE_DEFAULT_MESSAGE)]


def test_handle_instruct_approve_with_custom_message() -> None:
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "approve",
        "承認、よろしく",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.comment == "承認、よろしく"
    assert comments.posted == [("nosetech/project-a", 1, "承認、よろしく")]


def test_handle_instruct_instruct_requires_message() -> None:
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()

    with pytest.raises(ValueError):
        handle_instruct(
            "nosetech/project-a",
            1,
            "instruct",
            None,
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
        )


def test_handle_instruct_instruct_on_in_progress_does_not_change_label_but_dispatches() -> None:
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "instruct",
        "割り込み指示です",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.label == STATUS_IN_PROGRESS
    assert result.dispatched is True
    assert labels.labels == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 1, "割り込み指示です")]


def test_handle_instruct_instruct_on_in_review_transitions_to_in_progress() -> None:
    """レビュー待ちへの返信は差し戻し扱いでin-progressへ遷移し、レビュー待ち一覧から
    カードが消える（承認操作と同様。issue #95）。"""
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "instruct",
        "追加対応をお願いします",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.label == STATUS_IN_PROGRESS
    assert labels.labels == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 1, "追加対応をお願いします")]


def test_handle_instruct_unknown_action_raises() -> None:
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()

    with pytest.raises(ValueError):
        handle_instruct(
            "nosetech/project-a",
            1,
            "unknown",  # type: ignore[arg-type]
            "x",
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
        )


def test_handle_instruct_reject_action_no_longer_supported() -> None:
    """rejectは設計から廃止済み（docs/basic-design.md 2-3、issue #55）。

    未知のactionと同様にValueErrorになることを保証し、意図せず復活しないようにする。
    """
    labels = FakeLabels({STATUS_NEEDS_HUMAN_DECISION})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()

    with pytest.raises(ValueError):
        handle_instruct(
            "nosetech/project-a",
            1,
            "reject",  # type: ignore[arg-type]
            "理由をどうぞ",
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
        )


class FakeReviewMerge:
    def __init__(
        self,
        pr_number: int | None,
        *,
        branch: str = "feature/issue-30-something",
        fail_get_pr_branch: bool = False,
        fail_delete_branch: bool = False,
    ) -> None:
        self.pr_number = pr_number
        self.branch = branch
        self.fail_get_pr_branch = fail_get_pr_branch
        self.fail_delete_branch = fail_delete_branch
        self.resolve_calls: list[tuple[str, int]] = []
        self.merge_calls: list[tuple[str, int]] = []
        self.close_calls: list[tuple[str, int]] = []
        self.get_pr_branch_calls: list[tuple[str, int]] = []
        self.delete_branch_calls: list[tuple[str, str]] = []

    def resolve_pr_number(self, repo: str, issue_number: int) -> int | None:
        self.resolve_calls.append((repo, issue_number))
        return self.pr_number

    def merge_pr(self, repo: str, pr_number: int) -> None:
        self.merge_calls.append((repo, pr_number))

    def close_issue(self, repo: str, issue_number: int) -> None:
        self.close_calls.append((repo, issue_number))

    def get_pr_branch(self, repo: str, pr_number: int) -> str:
        self.get_pr_branch_calls.append((repo, pr_number))
        if self.fail_get_pr_branch:
            raise subprocess.CalledProcessError(1, ["gh", "api"])
        return self.branch

    def delete_branch(self, repo: str, branch: str) -> None:
        self.delete_branch_calls.append((repo, branch))
        if self.fail_delete_branch:
            raise subprocess.CalledProcessError(1, ["gh", "api"])


def test_handle_instruct_approve_on_in_review_merges_pr_and_closes_issue() -> None:
    """`Closes #`によるGitHubの自動クローズはデフォルトブランチへのマージ時にしか発動せず、

    本プロジェクトのワークフロー（`develop`へマージ）では発動しないため、マージ成功後は
    明示的にissueをクローズする必要がある（issue #58で自動クローズされない不具合が確認された）。
    ラベルも`status:closed`へ即時遷移させる必要がある。`status:in-review`のまま残すと、
    承認直後のStateStore同期更新（issue #70）でもレビュー待ち一覧からカードが消えない
    不具合になる（issue #70フォローアップ）。
    """
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")

    result = handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
    )

    assert result.action == "approve"
    assert result.dispatched is False
    assert result.label is None
    assert review_merge.resolve_calls == [("nosetech/project-a", 30)]
    assert review_merge.merge_calls == [("nosetech/project-a", 33)]
    assert review_merge.close_calls == [("nosetech/project-a", 30)]
    assert review_merge.get_pr_branch_calls == [("nosetech/project-a", 33)]
    assert review_merge.delete_branch_calls == [
        ("nosetech/project-a", "feature/issue-30-something")
    ]
    assert comments.posted == []
    assert labels.labels == {STATUS_CLOSED}
    assert calls == []


def test_handle_instruct_approve_on_in_review_swallows_get_pr_branch_failure() -> None:
    """ブランチ名解決の失敗は後始末の失敗に過ぎず、承認自体は成功として扱う（issue #72）。"""
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, fail_get_pr_branch=True)

    result = handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
    )

    assert result.action == "approve"
    assert review_merge.merge_calls == [("nosetech/project-a", 33)]
    assert review_merge.close_calls == [("nosetech/project-a", 30)]
    assert review_merge.delete_branch_calls == []
    assert labels.labels == {STATUS_CLOSED}


def test_handle_instruct_approve_on_in_review_swallows_delete_branch_failure() -> None:
    """ブランチ削除自体の失敗（保護ブランチ設定・削除済み等）も承認の成功を損なわない（issue #72）。

    `--delete-branch`をマージと同一コマンドに含めた場合、ブランチ削除だけの失敗で
    `close_issue`が実行されなくなる不具合の再発を避けるため、分離したステップで検証する。
    """
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, fail_delete_branch=True)

    result = handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
    )

    assert result.action == "approve"
    assert review_merge.merge_calls == [("nosetech/project-a", 33)]
    assert review_merge.close_calls == [("nosetech/project-a", 30)]
    assert review_merge.delete_branch_calls == [
        ("nosetech/project-a", "feature/issue-30-something")
    ]
    assert labels.labels == {STATUS_CLOSED}


def test_handle_instruct_approve_on_in_review_syncs_worktree_after_branch_delete() -> None:
    """ブランチ削除成功後、worktreeを`develop`へ同期する（issue #80）。"""
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")
    sync_calls: list[tuple[str, str]] = []

    def sync_worktree(worktree_path: str, branch: str) -> None:
        sync_calls.append((worktree_path, branch))

    result = handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        worktree_path="/path/to/worktree",
        sync_worktree=sync_worktree,
    )

    assert result.action == "approve"
    assert sync_calls == [("/path/to/worktree", "feature/issue-30-something")]


def test_handle_instruct_approve_on_in_review_reports_on_stage_in_order() -> None:
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")
    stages: list[str] = []

    handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        worktree_path="/path/to/worktree",
        sync_worktree=lambda worktree_path, branch: None,
        on_stage=stages.append,
    )

    assert stages == ["merge", "close", "label", "branch_delete", "worktree_sync"]


def test_handle_instruct_approve_on_in_review_reports_skipped_stages_when_delete_branch_fails() -> (
    None
):
    """ブランチ削除・worktree同期は失敗しても処理全体は成功扱いになるが、段階表示上は
    スキップとして区別できるよう、成功時と異なるstage名を通知する（issue #167）。
    """
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, fail_delete_branch=True)
    stages: list[str] = []

    handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        worktree_path="/path/to/worktree",
        sync_worktree=lambda worktree_path, branch: None,
        on_stage=stages.append,
    )

    assert stages == [
        "merge",
        "close",
        "label",
        "branch_delete_skipped",
        "worktree_sync_skipped",
    ]


def test_handle_instruct_approve_on_in_review_reports_worktree_skip_when_dispatch_running() -> None:
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")
    stages: list[str] = []

    # 同一リポジトリの別issueが実行中の状態を、実際にディスパッチをブロックして作る
    # （test_handle_instruct_approve_on_in_review_skips_worktree_sync_when_dispatch_running
    # と同じ手法）。
    release_event = threading.Event()
    started_event = threading.Event()

    def blocking_dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        started_event.set()
        release_event.wait(timeout=2)

    dispatch_queue = DispatchQueue(dispatch_fn=blocking_dispatch_fn)
    dispatch_queue.enqueue("nosetech/project-a", 2, "別issueが実行中")
    assert started_event.wait(timeout=2)

    try:
        handle_instruct(
            "nosetech/project-a",
            30,
            "approve",
            None,
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
            resolve_pr_number=review_merge.resolve_pr_number,
            merge_pr=review_merge.merge_pr,
            close_issue=review_merge.close_issue,
            get_pr_branch=review_merge.get_pr_branch,
            delete_branch=review_merge.delete_branch,
            worktree_path="/path/to/worktree",
            sync_worktree=lambda worktree_path, branch: None,
            on_stage=stages.append,
        )
    finally:
        release_event.set()

    assert stages == ["merge", "close", "label", "branch_delete", "worktree_sync_skipped"]


def test_handle_instruct_approve_on_in_review_skips_worktree_sync_without_worktree_path() -> None:
    """worktree_pathが渡されない（未配線の）呼び出し元では同期処理を行わない。"""
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")
    sync_calls: list[tuple[str, str]] = []

    def sync_worktree(worktree_path: str, branch: str) -> None:
        sync_calls.append((worktree_path, branch))

    handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=sync_worktree,
    )

    assert sync_calls == []


def test_handle_instruct_approve_on_in_review_skips_worktree_sync_when_delete_branch_fails() -> (
    None
):
    """ブランチ削除が失敗した場合、worktree同期も行わない（リモートに削除対象が残るため）。"""
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=33, fail_delete_branch=True)
    sync_calls: list[tuple[str, str]] = []

    def sync_worktree(worktree_path: str, branch: str) -> None:
        sync_calls.append((worktree_path, branch))

    handle_instruct(
        "nosetech/project-a",
        30,
        "approve",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        worktree_path="/path/to/worktree",
        sync_worktree=sync_worktree,
    )

    assert sync_calls == []


def test_handle_instruct_approve_on_in_review_skips_worktree_sync_when_dispatch_running() -> None:
    """同じプロジェクトの別issueでAgent Runnerが実行中の間はworktree同期をスキップする。

    実行中のAgent Runnerの作業ディレクトリを横から書き換えてセッションを破壊しないよう
    にするための配慮（issue #80）。
    """
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-30-something")
    sync_calls: list[tuple[str, str]] = []

    def sync_worktree(worktree_path: str, branch: str) -> None:
        sync_calls.append((worktree_path, branch))

    # 同一リポジトリの別issueが実行中の状態を、実際にディスパッチをブロックして作る。
    release_event = threading.Event()
    started_event = threading.Event()

    def blocking_dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        started_event.set()
        release_event.wait(timeout=2)

    dispatch_queue = DispatchQueue(dispatch_fn=blocking_dispatch_fn)
    dispatch_queue.enqueue("nosetech/project-a", 2, "別issueが実行中")
    assert started_event.wait(timeout=2)

    try:
        handle_instruct(
            "nosetech/project-a",
            30,
            "approve",
            None,
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
            resolve_pr_number=review_merge.resolve_pr_number,
            merge_pr=review_merge.merge_pr,
            close_issue=review_merge.close_issue,
            get_pr_branch=review_merge.get_pr_branch,
            delete_branch=review_merge.delete_branch,
            worktree_path="/path/to/worktree",
            sync_worktree=sync_worktree,
        )
    finally:
        release_event.set()

    assert review_merge.delete_branch_calls == [
        ("nosetech/project-a", "feature/issue-30-something")
    ]
    assert sync_calls == []


def test_handle_instruct_approve_on_in_review_without_linked_pr_raises() -> None:
    labels = FakeLabels({STATUS_IN_REVIEW})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()
    review_merge = FakeReviewMerge(pr_number=None)

    with pytest.raises(ReviewMergeError):
        handle_instruct(
            "nosetech/project-a",
            30,
            "approve",
            None,
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            post_comment=comments.post_comment,
            dispatch_queue=dispatch_queue,
            resolve_pr_number=review_merge.resolve_pr_number,
            merge_pr=review_merge.merge_pr,
            close_issue=review_merge.close_issue,
        )

    assert review_merge.merge_calls == []
    assert review_merge.close_calls == []
    assert comments.posted == []


class FakeIssueCreator:
    def __init__(self, number: int) -> None:
        self.number = number
        self.created: list[tuple[str, str, str]] = []

    def create_issue(self, repo: str, title: str, body: str) -> int:
        self.created.append((repo, title, body))
        return self.number


def test_handle_create_issue_immediate_dispatches() -> None:
    labels = FakeLabels(set())
    issue_creator = FakeIssueCreator(number=99)
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_create_issue(
        "nosetech/project-a",
        "新機能",
        "プロンプト本文",
        "immediate",
        create_issue=issue_creator.create_issue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert result.issue_number == 99
    assert result.dispatched is True
    assert issue_creator.created == [("nosetech/project-a", "新機能", "プロンプト本文")]
    assert labels.labels == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 99, "プロンプト本文")]


def test_handle_create_issue_queued_does_not_dispatch() -> None:
    labels = FakeLabels(set())
    issue_creator = FakeIssueCreator(number=99)
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_create_issue(
        "nosetech/project-a",
        "新機能",
        "プロンプト本文",
        "queued",
        create_issue=issue_creator.create_issue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert result.dispatched is False
    assert labels.labels == {STATUS_TODO}
    assert calls == []


def test_handle_instruct_reports_on_stage_in_order() -> None:
    labels = FakeLabels({STATUS_TODO})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    stages: list[str] = []

    handle_instruct(
        "nosetech/project-a",
        1,
        "instruct",
        "進めてください",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
        on_stage=stages.append,
    )

    _wait_for(calls, 1)
    assert stages == ["comment", "label", "dispatch"]


def test_handle_create_issue_immediate_reports_on_stage_in_order() -> None:
    labels = FakeLabels(set())
    issue_creator = FakeIssueCreator(number=99)
    dispatch_queue, calls = _synchronous_dispatch_queue()
    stages: list[str] = []

    handle_create_issue(
        "nosetech/project-a",
        "新機能",
        "プロンプト本文",
        "immediate",
        create_issue=issue_creator.create_issue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
        on_stage=stages.append,
    )

    _wait_for(calls, 1)
    assert stages == ["issue", "label", "dispatch"]


def test_handle_create_issue_queued_reports_on_stage_without_dispatch() -> None:
    labels = FakeLabels(set())
    issue_creator = FakeIssueCreator(number=99)
    dispatch_queue, _ = _synchronous_dispatch_queue()
    stages: list[str] = []

    handle_create_issue(
        "nosetech/project-a",
        "新機能",
        "プロンプト本文",
        "queued",
        create_issue=issue_creator.create_issue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
        on_stage=stages.append,
    )

    assert stages == ["issue", "label"]


def test_handle_create_issue_invalid_dispatch_raises() -> None:
    labels = FakeLabels(set())
    issue_creator = FakeIssueCreator(number=99)
    dispatch_queue, _ = _synchronous_dispatch_queue()

    with pytest.raises(ValueError):
        handle_create_issue(
            "nosetech/project-a",
            "新機能",
            "プロンプト本文",
            "later",  # type: ignore[arg-type]
            create_issue=issue_creator.create_issue,
            get_labels=labels.get_labels,
            add_label=labels.add_label,
            remove_label=labels.remove_label,
            dispatch_queue=dispatch_queue,
        )
