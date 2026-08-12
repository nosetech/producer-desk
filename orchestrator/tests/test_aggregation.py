"""orchestrator.aggregation の単体テスト。

docs/basic-design.md 2-2の集約仕様（判断待ち一覧・活動ログ）を検証する。
"""

from __future__ import annotations

import logging

import pytest

from orchestrator.aggregation import ActivityEvent, IssueSummary, aggregate
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)


def _issue(
    repo: str, number: int, labels: list[str], updated_at: str, title: str = "title"
) -> IssueSummary:
    return IssueSummary(
        repo=repo, number=number, title=title, labels=labels, comments=[], updated_at=updated_at
    )


def test_aggregate_collects_needs_human_decision_issues_across_repos() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-02T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 3, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [(i.repo, i.number) for i in state.decisions] == [
        ("nosetech/project-b", 3),
        ("nosetech/project-a", 2),
    ]


def test_aggregate_decisions_sorted_by_updated_at_descending() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-05T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [i.number for i in state.decisions] == [2, 1]


def test_aggregate_excludes_issues_without_needs_human_decision_label() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_PROGRESS], "2026-08-02T00:00:00Z"),
            _issue("nosetech/project-a", 3, [STATUS_IN_REVIEW], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.decisions == []


def test_aggregate_builds_activity_events_with_current_status_label() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_PROGRESS],
                "2026-08-01T00:00:00Z",
                title="機能A",
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.activity == [
        ActivityEvent(
            repo="nosetech/project-a",
            number=1,
            title="機能A",
            label=STATUS_IN_PROGRESS,
            updated_at="2026-08-01T00:00:00Z",
        )
    ]


def test_aggregate_activity_sorted_by_updated_at_descending_across_repos() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 2, [STATUS_IN_REVIEW], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [(e.repo, e.number) for e in state.activity] == [
        ("nosetech/project-b", 2),
        ("nosetech/project-a", 1),
    ]


def test_aggregate_excludes_issues_with_no_status_label_from_activity() -> None:
    # 状態ラベルが1つも付いていないissueは管理対象外として扱い、活動ログから除外する
    # （docs/basic-design.md 1章「管理対象外issueの扱い」、issue #45）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_PROGRESS], "2026-08-02T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [e.number for e in state.activity] == [2]


def test_aggregate_activity_includes_status_closed_issues() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_CLOSED], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.activity[0].label == STATUS_CLOSED


def test_aggregate_with_no_projects_returns_empty_state() -> None:
    state = aggregate({})

    assert state.decisions == []
    assert state.reviews == []
    assert state.activity == []


def test_aggregate_collects_in_review_issues_across_repos() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_REVIEW], "2026-08-02T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 3, [STATUS_IN_REVIEW], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [(i.repo, i.number) for i in state.reviews] == [
        ("nosetech/project-b", 3),
        ("nosetech/project-a", 2),
    ]


def test_aggregate_reviews_sorted_by_updated_at_descending() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_REVIEW], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_REVIEW], "2026-08-05T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert [i.number for i in state.reviews] == [2, 1]


def test_aggregate_excludes_issues_without_in_review_label_from_reviews() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-02T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.reviews == []


def test_aggregate_reviews_preserve_pr_number() -> None:
    issue = _issue("nosetech/project-a", 1, [STATUS_IN_REVIEW], "2026-08-01T00:00:00Z")
    issue.pr_number = 33
    issues_by_repo = {"nosetech/project-a": [issue]}

    state = aggregate(issues_by_repo)

    assert state.reviews[0].pr_number == 33


def test_aggregate_activity_prefers_in_review_over_stale_in_progress() -> None:
    # 非atomicなtransition_labelやAgent Runnerの遷移指示漏れにより、旧ラベル
    # (status:in-progress)が残ったまま新ラベル(status:in-review)が付与される
    # ケースを再現する（issue #77）。issue.labelsの並び順に関わらず、reviews
    # 一覧と矛盾しないよう進行が進んだstatus:in-reviewが採用されるべき。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_PROGRESS, STATUS_IN_REVIEW],
                "2026-08-01T00:00:00Z",
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.activity[0].label == STATUS_IN_REVIEW
    # 同じissueがreviews一覧にも一致して現れる（表示の食い違いが起きない）
    assert [i.number for i in state.reviews] == [1]


def test_aggregate_activity_prefers_needs_human_decision_over_stale_in_progress() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_NEEDS_HUMAN_DECISION, STATUS_IN_PROGRESS],
                "2026-08-01T00:00:00Z",
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.activity[0].label == STATUS_NEEDS_HUMAN_DECISION


def test_aggregate_activity_prefers_closed_over_stale_in_review() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_REVIEW, STATUS_CLOSED],
                "2026-08-01T00:00:00Z",
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.activity[0].label == STATUS_CLOSED


def test_aggregate_logs_warning_when_issue_has_multiple_status_labels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_PROGRESS, STATUS_IN_REVIEW],
                "2026-08-01T00:00:00Z",
            ),
        ],
    }

    with caplog.at_level(logging.WARNING, logger="orchestrator.aggregation"):
        aggregate(issues_by_repo)

    assert any(
        "project-a#1" in record.message and "複数の状態ラベル" in record.message
        for record in caplog.records
    )


def test_aggregate_does_not_log_warning_when_issue_has_single_status_label(
    caplog: pytest.LogCaptureFixture,
) -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_PROGRESS], "2026-08-01T00:00:00Z"),
        ],
    }

    with caplog.at_level(logging.WARNING, logger="orchestrator.aggregation"):
        aggregate(issues_by_repo)

    assert caplog.records == []
