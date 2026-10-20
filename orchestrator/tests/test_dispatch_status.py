"""orchestrator.dispatch_status の単体テスト（issue #215）。"""

from __future__ import annotations

import pytest

from orchestrator.aggregation import IssueSummary
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.dispatch_status import (
    REDISPATCH_COMMENT,
    IssueNotManagedError,
    NoPendingInstructionError,
    RedispatchConflictError,
    diagnose,
    handle_redispatch,
)
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.labels import STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION, STATUS_TODO

REPO = "nosetech/project-a"


def _issue(labels: list[str], bodies: list[str], state: str = "OPEN") -> IssueSummary:
    return IssueSummary(
        repo=REPO,
        number=1,
        title="t",
        labels=labels,
        comments=[{"id": f"c{i}", "body": b} for i, b in enumerate(bodies)],
        updated_at="2026-01-01T00:00:00Z",
        state=state,
    )


def _queue(calls: list | None = None) -> DispatchQueue:
    recorded = calls if calls is not None else []
    return DispatchQueue(dispatch_fn=lambda repo, n, m: recorded.append((repo, n, m)))


class _Labels:
    def __init__(self, initial: set[str]) -> None:
        self.labels = set(initial)

    def get(self, repo: str, n: int) -> set[str]:
        return set(self.labels)

    def add(self, repo: str, n: int, label: str) -> None:
        self.labels.add(label)

    def remove(self, repo: str, n: int, label: str) -> None:
        self.labels.discard(label)


def test_completed_when_no_comment_after_result() -> None:
    issue = _issue([STATUS_NEEDS_HUMAN_DECISION], ["指示", "Agent Runner実行結果:\n完了"])
    status = diagnose(issue, _queue())
    assert status.state == "completed"
    assert status.redispatchable is False


def test_not_dispatched_returns_last_instruction_after_result() -> None:
    issue = _issue(
        [STATUS_NEEDS_HUMAN_DECISION],
        ["Agent Runner実行結果:\nx", "古い指示", f"最新の指示\n\n{BOT_COMMENT_MARKER}"],
    )
    status = diagnose(issue, _queue())
    assert status.state == "not_dispatched"
    assert status.pending_message == "最新の指示"
    assert status.redispatchable is True


def test_no_result_comment_uses_all_comments_last_one() -> None:
    status = diagnose(_issue([STATUS_TODO], ["a", "b"]), _queue())
    assert status.pending_message == "b"


def test_no_comments_is_not_redispatchable() -> None:
    status = diagnose(_issue([STATUS_TODO], []), _queue())
    assert status.state == "completed"
    assert status.pending_message is None


def test_orphaned_in_progress() -> None:
    status = diagnose(_issue([STATUS_IN_PROGRESS], ["指示"]), _queue())
    assert status.state == "orphaned_in_progress"
    assert status.redispatchable is True


def test_not_managed_without_status_label_or_closed() -> None:
    assert diagnose(_issue([], ["x"]), _queue()).state == "not_managed"
    assert diagnose(_issue([STATUS_TODO], ["x"], state="CLOSED"), _queue()).state == "not_managed"


def test_redispatch_comment_acts_as_boundary() -> None:
    issue = _issue([STATUS_NEEDS_HUMAN_DECISION], ["指示", REDISPATCH_COMMENT])
    assert diagnose(issue, _queue()).pending_message is None


def test_running_and_queued() -> None:
    import threading

    release = threading.Event()
    started = threading.Event()

    def dispatch_fn(repo: str, n: int, m: str) -> None:
        started.set()
        release.wait(timeout=5)

    queue = DispatchQueue(dispatch_fn=dispatch_fn)
    queue.enqueue(REPO, 1, "m")
    assert started.wait(timeout=2)
    queue.enqueue(REPO, 2, "m")
    try:
        assert diagnose(_issue([STATUS_IN_PROGRESS], ["x"]), queue).state == "running"
        other = _issue([STATUS_IN_PROGRESS], ["x"])
        other.number = 2
        assert diagnose(other, queue).state == "queued"
    finally:
        release.set()


def test_redispatch_enqueues_without_posting_instruction_comment() -> None:
    calls: list = []
    done = __import__("threading").Event()
    queue = DispatchQueue(dispatch_fn=lambda r, n, m: (calls.append((r, n, m)), done.set()))
    labels = _Labels({STATUS_NEEDS_HUMAN_DECISION})
    posted: list[str] = []
    handle_redispatch(
        _issue([STATUS_NEEDS_HUMAN_DECISION], ["Agent Runner実行結果:\nx", "やって"]),
        get_labels=labels.get,
        add_label=labels.add,
        remove_label=labels.remove,
        post_comment=lambda r, n, b: posted.append(b),
        dispatch_queue=queue,
    )
    assert done.wait(timeout=2)
    assert calls == [(REPO, 1, "やって")]
    assert labels.labels == {STATUS_IN_PROGRESS}
    assert posted == [REDISPATCH_COMMENT]


def test_redispatch_errors() -> None:
    labels = _Labels(set())
    kwargs = dict(
        get_labels=labels.get,
        add_label=labels.add,
        remove_label=labels.remove,
        post_comment=lambda r, n, b: None,
        dispatch_queue=_queue(),
    )
    with pytest.raises(NoPendingInstructionError):
        handle_redispatch(_issue([STATUS_TODO], []), **kwargs)
    with pytest.raises(IssueNotManagedError):
        handle_redispatch(_issue([], ["x"]), **kwargs)


def test_redispatch_conflict_when_active() -> None:
    import threading

    release = threading.Event()
    started = threading.Event()
    queue = DispatchQueue(dispatch_fn=lambda r, n, m: (started.set(), release.wait(timeout=5)))
    queue.enqueue(REPO, 1, "m")
    assert started.wait(timeout=2)
    labels = _Labels({STATUS_IN_PROGRESS})
    try:
        with pytest.raises(RedispatchConflictError):
            handle_redispatch(
                _issue([STATUS_IN_PROGRESS], ["x"]),
                get_labels=labels.get,
                add_label=labels.add,
                remove_label=labels.remove,
                post_comment=lambda r, n, b: None,
                dispatch_queue=queue,
            )
    finally:
        release.set()
