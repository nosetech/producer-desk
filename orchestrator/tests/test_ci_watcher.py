"""orchestrator.ci_watcher の単体テスト。

issue #173: CI完了待機のため意図的にstatus:in-progressのまま終了したissueについて、
CI完了を検知したAgent Runnerの自動再開・タイムアウト時のneeds-human-decisionへの
フェイルセーフを検証する。gh CLI呼び出しはフェイクに差し替える。
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from orchestrator import agent_runner
from orchestrator.aggregation import IssueSummary
from orchestrator.ci_watcher import (
    CI_COMPLETED_RESUME_MESSAGE,
    CI_WAIT_TIMEOUT,
    CiWaitTracker,
    process_ci_waiting_issues,
)
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.labels import STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION


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


class FakeStatusCheckRollup:
    def __init__(self, rollup_by_pr: dict[int, list[dict]]) -> None:
        self.rollup_by_pr = rollup_by_pr
        self.calls: list[tuple[str, int]] = []

    def __call__(self, repo: str, pr_number: int) -> list[dict]:
        self.calls.append((repo, pr_number))
        return self.rollup_by_pr.get(pr_number, [])


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


def _ci_wait_comment(pr_number: int) -> dict:
    body = (
        "Agent Runner実行結果:\nCIの完了を待っています。\n\n"
        f'{agent_runner.CI_WAIT_MARKER_PREFIX}\n{{"pr_number": {pr_number}}}\n-->'
        f"\n\n{BOT_COMMENT_MARKER}"
    )
    return {"id": "c1", "body": body}


def _issue(repo: str, number: int, labels: list[str], comments: list[dict]) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title="t",
        labels=labels,
        comments=comments,
        updated_at="2026-09-03T00:00:00Z",
        state="OPEN",
    )


def test_resumes_agent_runner_when_ci_completed() -> None:
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({172: [{"status": "COMPLETED", "conclusion": "SUCCESS"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 173, [STATUS_IN_PROGRESS], [_ci_wait_comment(172)])
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )

    _wait_for(calls, 1)
    assert calls == [("nosetech/project-a", 173, CI_COMPLETED_RESUME_MESSAGE)]
    assert labels.labels == {STATUS_IN_PROGRESS}
    assert comments.posted == []


def test_does_not_dispatch_when_ci_still_pending() -> None:
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({172: [{"status": "IN_PROGRESS"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 173, [STATUS_IN_PROGRESS], [_ci_wait_comment(172)])
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )

    time.sleep(0.05)
    assert calls == []
    assert labels.labels == {STATUS_IN_PROGRESS}


def test_recognizes_legacy_state_pending_field() -> None:
    """`status`（Checks API）ではなく`state`（レガシーCommit Status API）で

    表現されるチェックも待機中として扱えることを確認する。
    """
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({172: [{"state": "PENDING"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 173, [STATUS_IN_PROGRESS], [_ci_wait_comment(172)])
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )

    time.sleep(0.05)
    assert calls == []


def test_ignores_issue_without_ci_wait_marker() -> None:
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                173,
                [STATUS_IN_PROGRESS],
                [{"id": "c1", "body": f"作業中です。\n\n{BOT_COMMENT_MARKER}"}],
            )
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )

    time.sleep(0.05)
    assert calls == []
    assert get_rollup.calls == []


def test_ignores_issue_not_in_progress() -> None:
    """CI待機マーカーが最新コメントに残っていても、既にstatus:in-progressから

    遷移済みならスキップする（レビュー待ち等に進行済みのissueへの誤爆防止）。
    """
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_NEEDS_HUMAN_DECISION})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({172: [{"status": "COMPLETED"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                173,
                [STATUS_NEEDS_HUMAN_DECISION],
                [_ci_wait_comment(172)],
            )
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )

    time.sleep(0.05)
    assert calls == []
    assert get_rollup.calls == []


def test_falls_back_to_needs_human_decision_after_timeout() -> None:
    """修正方針5: 無限待機防止のフェイルセーフ。

    CI_WAIT_TIMEOUTを超えてもCIが完了しない場合、needs-human-decisionへ
    遷移させることを確認する。
    """
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()
    dispatch_queue, calls = _synchronous_dispatch_queue()
    get_rollup = FakeStatusCheckRollup({172: [{"status": "IN_PROGRESS"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 173, [STATUS_IN_PROGRESS], [_ci_wait_comment(172)])
        ],
    }

    start = datetime(2026, 9, 3, 0, 0, 0, tzinfo=UTC)
    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
        now=lambda: start,
    )
    assert labels.labels == {STATUS_IN_PROGRESS}

    after_timeout = start + CI_WAIT_TIMEOUT + timedelta(seconds=1)
    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
        now=lambda: after_timeout,
    )

    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert calls == []
    assert len(comments.posted) == 1
    assert "PR #172" in comments.posted[0][2]


def test_does_not_double_dispatch_while_issue_is_active() -> None:
    """resume済みでまだ処理中（`dispatch_queue.is_active`がTrue）のissueは

    スキップし、二重ディスパッチしないことを確認する。
    """
    tracker = CiWaitTracker()
    labels = FakeLabels({STATUS_IN_PROGRESS})
    comments = FakeComments()

    calls: list[tuple[str, int, str]] = []
    started = threading.Event()
    release = threading.Event()

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        calls.append((repo, issue_number, message))
        started.set()
        release.wait(timeout=2.0)

    dispatch_queue = DispatchQueue(dispatch_fn=dispatch_fn)
    get_rollup = FakeStatusCheckRollup({172: [{"status": "COMPLETED"}]})
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 173, [STATUS_IN_PROGRESS], [_ci_wait_comment(172)])
        ],
    }

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )
    assert started.wait(timeout=2.0)

    process_ci_waiting_issues(
        issues_by_repo,
        tracker,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        get_pr_status_check_rollup=get_rollup,
        dispatch_queue=dispatch_queue,
        post_comment=comments.post_comment,
    )
    release.set()

    assert len(calls) == 1
