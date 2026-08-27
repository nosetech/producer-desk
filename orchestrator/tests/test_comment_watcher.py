"""orchestrator.comment_watcher の単体テスト。

docs/basic-design.md 2-3「共通仕様」の、直接issueにコメントされた指示を
ポーリングで検知するフローを検証する。
"""

from __future__ import annotations

import time

from orchestrator.aggregation import IssueSummary
from orchestrator.comment_watcher import CommentTracker, process_new_comments
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)


class FakeLabels:
    def __init__(self, initial: dict[int, set[str]]) -> None:
        self.labels_by_issue = initial

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        return set(self.labels_by_issue.get(issue_number, set()))

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels_by_issue.setdefault(issue_number, set()).add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels_by_issue.setdefault(issue_number, set()).discard(label)


def _synchronous_dispatch_queue() -> tuple[DispatchQueue, list[tuple[str, int, str]]]:
    calls: list[tuple[str, int, str]] = []

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        calls.append((repo, issue_number, message))

    return DispatchQueue(dispatch_fn=dispatch_fn), calls


def _wait_for(calls: list, count: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(calls) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"expected {count} dispatch calls, got {len(calls)}")


def _issue(
    repo: str,
    number: int,
    labels: list[str],
    comments: list[dict],
    *,
    state: str = "OPEN",
) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title="t",
        labels=labels,
        comments=comments,
        updated_at="2026-08-01T00:00:00Z",
        state=state,
    )


def test_first_observation_seeds_known_comments_without_dispatching() -> None:
    tracker = CommentTracker()
    labels = FakeLabels({1: {STATUS_TODO}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_TODO],
                [{"id": "c1", "body": "既存のコメント"}],
            )
        ]
    }

    process_new_comments(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert calls == []
    assert labels.labels_by_issue[1] == {STATUS_TODO}


def test_new_comment_after_first_observation_triggers_dispatch() -> None:
    tracker = CommentTracker()
    labels = FakeLabels({1: {STATUS_TODO}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    first_poll = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], [{"id": "c1", "body": "既存のコメント"}])
        ]
    }
    process_new_comments(
        first_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    second_poll = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_TODO],
                [
                    {"id": "c1", "body": "既存のコメント"},
                    {"id": "c2", "body": "承認します。進めてください。"},
                ],
            )
        ]
    }
    process_new_comments(
        second_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert labels.labels_by_issue[1] == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 1, "承認します。進めてください。")]


def test_no_new_comments_does_not_dispatch_again() -> None:
    tracker = CommentTracker()
    labels = FakeLabels({1: {STATUS_TODO}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    issues = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], [{"id": "c1", "body": "既存のコメント"}])
        ]
    }
    process_new_comments(
        issues,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )
    process_new_comments(
        issues,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert calls == []


def test_new_comment_on_needs_human_decision_issue_transitions_to_in_progress() -> None:
    tracker = CommentTracker()
    labels = FakeLabels({5: {STATUS_NEEDS_HUMAN_DECISION}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    issues_v1 = {
        "nosetech/project-a": [_issue("nosetech/project-a", 5, [STATUS_NEEDS_HUMAN_DECISION], [])]
    }
    process_new_comments(
        issues_v1,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    issues_v2 = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                5,
                [STATUS_NEEDS_HUMAN_DECISION],
                [{"id": "c1", "body": "承認します。進めてください。"}],
            )
        ]
    }
    process_new_comments(
        issues_v2,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert labels.labels_by_issue[5] == {STATUS_IN_PROGRESS}
    _wait_for(calls, 1)


def test_bot_authored_comment_does_not_trigger_redispatch() -> None:
    """issue #33の再発防止テスト。

    Agent Runnerが実行結果をissueコメントとして投稿すると、そのコメント自体が
    次回ポーリングで「新規コメント」として観測される。マーカーが無ければこれを
    新規の人間指示と誤検知し、無限に再ディスパッチし続けてしまう。
    """
    tracker = CommentTracker()
    labels = FakeLabels({1: {STATUS_IN_PROGRESS}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    first_poll = {"nosetech/project-a": [_issue("nosetech/project-a", 1, [STATUS_IN_PROGRESS], [])]}
    process_new_comments(
        first_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    second_poll = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_PROGRESS],
                [
                    {
                        "id": "c1",
                        "body": f"Agent Runner実行結果:\n完了しました\n\n{BOT_COMMENT_MARKER}",
                    }
                ],
            )
        ]
    }
    process_new_comments(
        second_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert calls == []
    assert labels.labels_by_issue[1] == {STATUS_IN_PROGRESS}


def test_new_comment_on_unmanaged_issue_does_not_trigger_dispatch() -> None:
    """issue #150の再発防止テスト。

    `labels.STATUS_LABELS`のいずれも付いていないissue（producer-desk管理対象外の、
    設計ドキュメントの議論用issue等）に新規コメントが投稿されても、指示として
    誤検知して`status:in-progress`への遷移・Agent Runnerのディスパッチを行っては
    ならない。
    """
    tracker = CommentTracker()
    labels = FakeLabels({1: set()})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    first_poll = {"nosetech/project-a": [_issue("nosetech/project-a", 1, [], [])]}
    process_new_comments(
        first_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    second_poll = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [],
                [{"id": "c1", "body": "対応を進めてください"}],
            )
        ]
    }
    process_new_comments(
        second_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert calls == []
    assert labels.labels_by_issue[1] == set()


def test_new_comment_on_closed_issue_does_not_trigger_dispatch() -> None:
    """issue #45の再発防止テスト。

    PRマージに伴うissueクローズと同時に投稿したコメント（作業再開の指示ではない）が、
    新規コメントとして誤って指示扱いされ、`status:closed`から`status:in-progress`への
    遷移とAgent Runnerの再ディスパッチを引き起こしてはならない。
    """
    tracker = CommentTracker()
    labels = FakeLabels({1: {STATUS_CLOSED}})
    dispatch_queue, calls = _synchronous_dispatch_queue()

    first_poll = {
        "nosetech/project-a": [_issue("nosetech/project-a", 1, [STATUS_CLOSED], [], state="CLOSED")]
    }
    process_new_comments(
        first_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    second_poll = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_CLOSED],
                [{"id": "c1", "body": "PRをマージしたのでクローズします。"}],
                state="CLOSED",
            )
        ]
    }
    process_new_comments(
        second_poll,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=dispatch_queue,
    )

    assert calls == []
    assert labels.labels_by_issue[1] == {STATUS_CLOSED}
