"""orchestrator.polling の単体テスト。gh呼び出し・待機はフェイクに差し替える。"""

from __future__ import annotations

import threading

from orchestrator.aggregation import IssueSummary
from orchestrator.config import Project
from orchestrator.labels import STATUS_IN_REVIEW, STATUS_NEEDS_HUMAN_DECISION
from orchestrator.polling import poll_once, run_polling_loop

PROJECT_A = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")
PROJECT_B = Project(repo="nosetech/project-b", worktree_path="/tmp/project-b")


def _issue(repo: str, number: int, labels: list[str]) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title="t",
        labels=labels,
        comments=[],
        updated_at="2026-08-01T00:00:00Z",
    )


def test_poll_once_fetches_each_project_and_aggregates() -> None:
    fixtures = {
        "nosetech/project-a": [_issue("nosetech/project-a", 1, [STATUS_NEEDS_HUMAN_DECISION])],
        "nosetech/project-b": [],
    }

    def list_issues(repo: str) -> list[IssueSummary]:
        return fixtures[repo]

    state = poll_once([PROJECT_A, PROJECT_B], list_issues=list_issues)

    assert [(i.repo, i.number) for i in state.decisions] == [("nosetech/project-a", 1)]


def test_poll_once_resolves_pr_number_only_for_in_review_issues() -> None:
    fixtures = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_REVIEW]),
            _issue("nosetech/project-a", 2, [STATUS_NEEDS_HUMAN_DECISION]),
        ],
    }
    resolved_calls: list[tuple[str, int]] = []

    def list_issues(repo: str) -> list[IssueSummary]:
        return fixtures[repo]

    def resolve_pr_number(repo: str, issue_number: int) -> int | None:
        resolved_calls.append((repo, issue_number))
        return 33

    state = poll_once([PROJECT_A], list_issues=list_issues, resolve_pr_number=resolve_pr_number)

    assert resolved_calls == [("nosetech/project-a", 1)]
    assert state.reviews[0].pr_number == 33


def test_run_polling_loop_calls_on_update_each_cycle_until_stopped() -> None:
    call_count = 0
    updates: list[int] = []
    stop_event = threading.Event()

    def list_issues(repo: str) -> list[IssueSummary]:
        return []

    def on_update(state: object) -> None:
        nonlocal call_count
        call_count += 1
        updates.append(call_count)
        if call_count >= 3:
            stop_event.set()

    run_polling_loop(
        [PROJECT_A],
        interval_seconds=0,
        on_update=on_update,
        list_issues=list_issues,
        stop_event=stop_event,
    )

    assert updates == [1, 2, 3]


def test_run_polling_loop_stops_immediately_when_stop_event_already_set() -> None:
    updates: list[int] = []
    stop_event = threading.Event()
    stop_event.set()

    def list_issues(repo: str) -> list[IssueSummary]:
        return []

    def on_update(state: object) -> None:
        updates.append(1)

    run_polling_loop(
        [PROJECT_A],
        interval_seconds=0,
        on_update=on_update,
        list_issues=list_issues,
        stop_event=stop_event,
    )

    # stop_eventが既にセット済みでも、最初の1回は実行してから停止する
    assert updates == [1]
