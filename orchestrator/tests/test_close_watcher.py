"""orchestrator.close_watcher の単体テスト。

docs/basic-design.md 1章「状態一覧・遷移条件・ラベル操作」の、クローズ検知による
`status:closed`遷移を検証する。gh CLI呼び出しはフェイクに差し替える。
"""

from __future__ import annotations

from orchestrator.aggregation import IssueSummary
from orchestrator.close_watcher import close_finished_issues
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_TODO,
)


class FakeGitHub:
    def __init__(self, initial_labels: set[str]) -> None:
        self.labels = set(initial_labels)
        self.calls: list[tuple[str, ...]] = []

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        self.calls.append(("get",))
        return set(self.labels)

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.calls.append(("add", label))
        self.labels.add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.calls.append(("remove", label))
        self.labels.discard(label)


def _issue(number: int, labels: list[str], state: str) -> IssueSummary:
    return IssueSummary(
        repo="nosetech/project-a",
        number=number,
        title="t",
        labels=labels,
        comments=[],
        updated_at="2026-08-01T00:00:00Z",
        state=state,
    )


def test_transitions_closed_issue_with_active_label_to_status_closed() -> None:
    fake = FakeGitHub({STATUS_IN_REVIEW})
    issues_by_repo = {
        "nosetech/project-a": [_issue(1, [STATUS_IN_REVIEW], state="CLOSED")],
    }

    close_finished_issues(
        issues_by_repo,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )

    assert fake.labels == {STATUS_CLOSED}


def test_leaves_open_issue_untouched() -> None:
    fake = FakeGitHub({STATUS_IN_PROGRESS})
    issues_by_repo = {
        "nosetech/project-a": [_issue(1, [STATUS_IN_PROGRESS], state="OPEN")],
    }

    close_finished_issues(
        issues_by_repo,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )

    assert fake.calls == []
    assert fake.labels == {STATUS_IN_PROGRESS}


def test_ignores_closed_issue_without_any_status_label() -> None:
    # 管理対象外issue（一度もproducer-deskが状態ラベルを付けていない）は対象外
    # （docs/basic-design.md 1章「管理対象外issueの扱い」）。
    fake = FakeGitHub(set())
    issues_by_repo = {
        "nosetech/project-a": [_issue(1, [], state="CLOSED")],
    }

    close_finished_issues(
        issues_by_repo,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )

    assert fake.calls == []
    assert fake.labels == set()


def test_noop_when_already_status_closed() -> None:
    # status:closedはACTIVE_STATUS_LABELSに含まれないため、既に付与済みなら
    # get_labels自体を呼ばずスキップする（無駄なgh呼び出しを避ける）。
    fake = FakeGitHub({STATUS_CLOSED})
    issues_by_repo = {
        "nosetech/project-a": [_issue(1, [STATUS_CLOSED], state="CLOSED")],
    }

    close_finished_issues(
        issues_by_repo,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )

    assert fake.calls == []
    assert fake.labels == {STATUS_CLOSED}


def test_processes_issues_across_multiple_repos() -> None:
    fake = FakeGitHub({STATUS_TODO})
    issues_by_repo = {
        "nosetech/project-a": [_issue(1, [STATUS_TODO], state="CLOSED")],
        "nosetech/project-b": [_issue(2, [STATUS_IN_PROGRESS], state="OPEN")],
    }

    close_finished_issues(
        issues_by_repo,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )

    assert ("add", STATUS_CLOSED) in fake.calls
