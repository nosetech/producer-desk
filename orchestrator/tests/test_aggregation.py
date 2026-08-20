"""orchestrator.aggregation の単体テスト。

docs/basic-design.md 2-2の集約仕様（判断待ち一覧・プロジェクト状況）を検証する。
"""

from __future__ import annotations

import logging

import pytest

from orchestrator.aggregation import STATUS_COUNT_UNTAGGED, IssueSummary, aggregate
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)


def _issue(
    repo: str,
    number: int,
    labels: list[str],
    updated_at: str,
    title: str = "title",
    state: str = "OPEN",
) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title=title,
        labels=labels,
        comments=[],
        updated_at=updated_at,
        state=state,
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


def test_aggregate_builds_project_status_with_current_status_label() -> None:
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

    assert len(state.project_status) == 1
    project = state.project_status[0]
    assert project.repo == "nosetech/project-a"
    assert project.label == STATUS_IN_PROGRESS
    assert project.number == 1
    assert project.title == "機能A"


def test_aggregate_project_status_reports_latest_issue_per_repo() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 2, [STATUS_IN_REVIEW], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    by_repo = {p.repo: p for p in state.project_status}
    assert by_repo["nosetech/project-a"].label == STATUS_TODO
    assert by_repo["nosetech/project-a"].number == 1
    assert by_repo["nosetech/project-b"].label == STATUS_IN_REVIEW
    assert by_repo["nosetech/project-b"].number == 2


def test_aggregate_project_status_ignores_issues_with_no_status_label() -> None:
    # 状態ラベルが1つも付いていないissueは管理対象外として扱い、プロジェクト状況の
    # 直近状態の算出から除外する（docs/basic-design.md 1章「管理対象外issueの扱い」、issue #45）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_PROGRESS], "2026-08-02T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.project_status[0].number == 2


def test_aggregate_project_status_is_none_when_repo_has_no_labeled_issues() -> None:
    issues_by_repo = {
        "nosetech/project-a": [_issue("nosetech/project-a", 1, [], "2026-08-01T00:00:00Z")]
    }

    state = aggregate(issues_by_repo)

    assert state.project_status[0].label is None
    assert state.project_status[0].number is None
    assert state.project_status[0].title is None


def test_aggregate_project_status_includes_status_closed_issues() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_CLOSED], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.project_status[0].label == STATUS_CLOSED


def test_aggregate_with_no_projects_returns_empty_state() -> None:
    state = aggregate({})

    assert state.decisions == []
    assert state.reviews == []
    assert state.project_status == []


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


def test_aggregate_project_status_prefers_in_review_over_stale_in_progress() -> None:
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

    assert state.project_status[0].label == STATUS_IN_REVIEW
    # 同じissueがreviews一覧にも一致して現れる（表示の食い違いが起きない）
    assert [i.number for i in state.reviews] == [1]


def test_aggregate_project_status_prefers_needs_human_decision_over_stale_in_progress() -> None:
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

    assert state.project_status[0].label == STATUS_NEEDS_HUMAN_DECISION


def test_aggregate_project_status_prefers_closed_over_stale_in_review() -> None:
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

    assert state.project_status[0].label == STATUS_CLOSED


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


def test_aggregate_marks_in_progress_issue_as_orphaned_when_dispatch_inactive() -> None:
    # ラベルのみ手動付与され、ディスパッチキューには一度も乗らなかったケースを再現する
    # （issue #50、実例: nosetech/stock-is#103）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_PROGRESS], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo, is_dispatch_active=lambda repo, number: False)

    assert state.project_status[0].is_orphaned is True


def test_aggregate_does_not_mark_in_progress_issue_as_orphaned_when_dispatch_active() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_PROGRESS], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo, is_dispatch_active=lambda repo, number: True)

    assert state.project_status[0].is_orphaned is False


def test_aggregate_does_not_mark_non_in_progress_issue_as_orphaned() -> None:
    # in-progress以外の状態は、ディスパッチキューに乗っていなくても正常（判断待ち・
    # レビュー待ち等はAgent Runner終了後の状態のため）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo, is_dispatch_active=lambda repo, number: False)

    assert state.project_status[0].is_orphaned is False


def test_aggregate_defaults_orphaned_to_false_when_is_dispatch_active_not_provided() -> None:
    # is_dispatch_activeを渡さない呼び出し元（判定不能）では、誤検知を避けて常にFalse。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_IN_PROGRESS], "2026-08-01T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.project_status[0].is_orphaned is False


def test_aggregate_status_counts_by_label_across_repos() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_PROGRESS], "2026-08-02T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 3, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-03T00:00:00Z"),
            _issue("nosetech/project-b", 4, [STATUS_IN_REVIEW], "2026-08-04T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.status_counts == {
        STATUS_TODO: 1,
        STATUS_IN_PROGRESS: 1,
        STATUS_NEEDS_HUMAN_DECISION: 1,
        STATUS_IN_REVIEW: 1,
        STATUS_COUNT_UNTAGGED: 0,
    }


def test_aggregate_status_counts_includes_untagged_issues() -> None:
    # 5つの状態ラベルいずれも付いていないissue（ラベル付け漏れの検知用途、issue #115）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, ["bug"], "2026-08-02T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.status_counts[STATUS_COUNT_UNTAGGED] == 2


def test_aggregate_status_counts_excludes_closed_status_label() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a", 1, [STATUS_CLOSED], "2026-08-01T00:00:00Z", state="CLOSED"
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert sum(state.status_counts.values()) == 0


def test_aggregate_status_counts_excludes_closed_state_issues_even_without_closed_label() -> None:
    # status:closedラベルが付かないまま人手で直接クローズされたケースを混入させない
    # （issue #115、`state == "OPEN"`に限定する方針）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue(
                "nosetech/project-a",
                1,
                [STATUS_IN_PROGRESS],
                "2026-08-01T00:00:00Z",
                state="CLOSED",
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert sum(state.status_counts.values()) == 0


def test_aggregate_status_counts_resolves_multiple_labels_by_priority() -> None:
    # 複数の状態ラベルが同時に付与されている場合、活動ログと同じ優先順位で1つに
    # 解決する（issue #77の優先順位ロジックを件数集計でも再利用）。
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

    assert state.status_counts[STATUS_IN_REVIEW] == 1
    assert state.status_counts[STATUS_IN_PROGRESS] == 0


def test_aggregate_status_counts_empty_when_no_issues() -> None:
    state = aggregate({})

    assert sum(state.status_counts.values()) == 0


def test_aggregate_project_status_counts_are_scoped_to_the_repo() -> None:
    # 「並行状況」ウィジェットの各チップが表示する件数は、そのリポジトリ単体の内訳
    # であり、他リポジトリのissueを含まない（issue #121）。
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [STATUS_TODO], "2026-08-01T00:00:00Z"),
            _issue("nosetech/project-a", 2, [STATUS_IN_PROGRESS], "2026-08-02T00:00:00Z"),
        ],
        "nosetech/project-b": [
            _issue("nosetech/project-b", 3, [STATUS_NEEDS_HUMAN_DECISION], "2026-08-03T00:00:00Z"),
        ],
    }

    state = aggregate(issues_by_repo)

    by_repo = {p.repo: p for p in state.project_status}
    assert by_repo["nosetech/project-a"].counts == {
        STATUS_TODO: 1,
        STATUS_IN_PROGRESS: 1,
        STATUS_NEEDS_HUMAN_DECISION: 0,
        STATUS_IN_REVIEW: 0,
        STATUS_COUNT_UNTAGGED: 0,
    }
    assert by_repo["nosetech/project-b"].counts == {
        STATUS_TODO: 0,
        STATUS_IN_PROGRESS: 0,
        STATUS_NEEDS_HUMAN_DECISION: 1,
        STATUS_IN_REVIEW: 0,
        STATUS_COUNT_UNTAGGED: 0,
    }


def test_aggregate_project_status_counts_include_untagged_and_exclude_closed() -> None:
    issues_by_repo = {
        "nosetech/project-a": [
            _issue("nosetech/project-a", 1, [], "2026-08-01T00:00:00Z"),
            _issue(
                "nosetech/project-a", 2, [STATUS_CLOSED], "2026-08-02T00:00:00Z", state="CLOSED"
            ),
        ],
    }

    state = aggregate(issues_by_repo)

    assert state.project_status[0].counts[STATUS_COUNT_UNTAGGED] == 1
    assert sum(state.project_status[0].counts.values()) == 1
