"""orchestrator.instruct の単体テスト。

docs/basic-design.md 2-3（指示出しAPI）・5-3（内部処理フロー）の仕様を検証する。
gh呼び出し・ディスパッチキューはフェイクに差し替える。
"""

from __future__ import annotations

import pytest

from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.instruct import (
    APPROVE_DEFAULT_MESSAGE,
    REJECT_DEFAULT_MESSAGE,
    handle_create_issue,
    handle_instruct,
)
from orchestrator.labels import (
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


def test_handle_instruct_reject_keeps_label_and_does_not_dispatch() -> None:
    labels = FakeLabels({STATUS_NEEDS_HUMAN_DECISION})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "reject",
        "理由をどうぞ",
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.comment == "理由をどうぞ"
    assert result.label is None
    assert result.dispatched is False
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert calls == []


def test_handle_instruct_reject_uses_default_message_when_omitted() -> None:
    labels = FakeLabels({STATUS_NEEDS_HUMAN_DECISION})
    comments = FakeComments()
    dispatch_queue, _ = _synchronous_dispatch_queue()

    result = handle_instruct(
        "nosetech/project-a",
        1,
        "reject",
        None,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        dispatch_queue=dispatch_queue,
    )

    assert result.comment == REJECT_DEFAULT_MESSAGE


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


def test_handle_instruct_instruct_on_in_review_keeps_label() -> None:
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

    assert result.label == STATUS_IN_REVIEW
    assert labels.labels == {STATUS_IN_REVIEW}


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
