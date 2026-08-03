"""orchestrator.labels の単体テスト。

docs/basic-design.md 1章の冪等な状態遷移フローと、自由記述指示によるラベル
遷移ルールの表を検証する。gh CLI呼び出しはフェイクに差し替えてテストする。
"""

from __future__ import annotations

import pytest

from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
    resolve_instruction_label,
    transition_label,
)


class FakeGitHub:
    """gh CLI呼び出しのフェイク。呼び出し履歴とラベル状態の変化を記録する。"""

    def __init__(self, initial_labels: set[str]) -> None:
        self.labels = set(initial_labels)
        self.calls: list[tuple[str, ...]] = []
        self.fail_get = False
        self.fail_add_labels: set[str] = set()
        self.fail_remove_labels: set[str] = set()

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        self.calls.append(("get",))
        if self.fail_get:
            raise RuntimeError("gh issue view failed")
        return set(self.labels)

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.calls.append(("add", label))
        if label in self.fail_add_labels:
            raise RuntimeError(f"failed to add label: {label}")
        self.labels.add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.calls.append(("remove", label))
        if label in self.fail_remove_labels:
            raise RuntimeError(f"failed to remove label: {label}")
        self.labels.discard(label)


def _transition(fake: FakeGitHub, new_label: str) -> None:
    transition_label(
        "nosetech/example",
        1,
        new_label,
        get_labels=fake.get_labels,
        add_label=fake.add_label,
        remove_label=fake.remove_label,
    )


def test_noop_when_target_label_already_present() -> None:
    fake = FakeGitHub({STATUS_IN_PROGRESS})

    _transition(fake, STATUS_IN_PROGRESS)

    assert fake.calls == [("get",)]
    assert fake.labels == {STATUS_IN_PROGRESS}


def test_noop_leaves_lingering_labels_untouched_when_target_already_present() -> None:
    # 目的のラベルが既に付いていれば、他の状態ラベルが残っていても何もしない
    # （docs/basic-design.md 1章の擬似コードに忠実な仕様上の挙動）。
    fake = FakeGitHub({STATUS_IN_PROGRESS, STATUS_TODO})

    _transition(fake, STATUS_IN_PROGRESS)

    assert fake.calls == [("get",)]
    assert fake.labels == {STATUS_IN_PROGRESS, STATUS_TODO}


def test_normal_transition_removes_old_and_adds_new() -> None:
    fake = FakeGitHub({STATUS_TODO})

    _transition(fake, STATUS_IN_PROGRESS)

    assert fake.calls == [("get",), ("remove", STATUS_TODO), ("add", STATUS_IN_PROGRESS)]
    assert fake.labels == {STATUS_IN_PROGRESS}


def test_removes_all_status_labels_present_before_adding_new() -> None:
    # PoCで判明した非atomic操作の結果、複数の状態ラベルが残ってしまうケースへの防御。
    fake = FakeGitHub({STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION})

    _transition(fake, STATUS_IN_REVIEW)

    removed = {call[1] for call in fake.calls if call[0] == "remove"}
    assert removed == {STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION}
    assert fake.calls[0] == ("get",)
    assert fake.calls[-1] == ("add", STATUS_IN_REVIEW)
    assert fake.labels == {STATUS_IN_REVIEW}


def test_get_labels_failure_propagates_without_mutating_labels() -> None:
    fake = FakeGitHub({STATUS_TODO})
    fake.fail_get = True

    with pytest.raises(RuntimeError):
        _transition(fake, STATUS_IN_PROGRESS)

    assert fake.calls == [("get",)]
    assert fake.labels == {STATUS_TODO}


def test_retry_converges_after_partial_remove_failure() -> None:
    fake = FakeGitHub({STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION})
    fake.fail_remove_labels = {STATUS_NEEDS_HUMAN_DECISION}

    with pytest.raises(RuntimeError):
        _transition(fake, STATUS_IN_REVIEW)

    # 失敗したラベルの除去は反映されず、目的のラベルもまだ付与されていない
    assert STATUS_NEEDS_HUMAN_DECISION in fake.labels
    assert STATUS_IN_REVIEW not in fake.labels

    # リトライ（今度は失敗なし）で収束する
    fake.fail_remove_labels = set()
    fake.calls.clear()
    _transition(fake, STATUS_IN_REVIEW)

    assert fake.labels == {STATUS_IN_REVIEW}


def test_retry_converges_after_add_failure_leaves_no_status_label() -> None:
    # 旧ラベルの除去には成功したが新ラベルの付与に失敗した状態（中途半端な状態）を再現。
    fake = FakeGitHub(set())  # 除去済み・未付与の状態からリトライ開始

    _transition(fake, STATUS_IN_PROGRESS)

    assert fake.calls == [("get",), ("add", STATUS_IN_PROGRESS)]
    assert fake.labels == {STATUS_IN_PROGRESS}


@pytest.mark.parametrize(
    ("current_labels", "expected"),
    [
        ({STATUS_TODO}, STATUS_IN_PROGRESS),
        ({STATUS_NEEDS_HUMAN_DECISION}, STATUS_IN_PROGRESS),
        ({STATUS_IN_PROGRESS}, STATUS_IN_PROGRESS),
        ({STATUS_IN_REVIEW}, STATUS_IN_REVIEW),
    ],
)
def test_resolve_instruction_label_follows_table(
    current_labels: set[str], expected: str
) -> None:
    assert resolve_instruction_label(current_labels) == expected


def test_resolve_instruction_label_defaults_to_in_progress_without_status_label() -> None:
    assert resolve_instruction_label(set()) == STATUS_IN_PROGRESS
