"""orchestrator.polling の単体テスト。gh呼び出し・待機はフェイクに差し替える。"""

from __future__ import annotations

import threading

from orchestrator.aggregation import IssueSummary
from orchestrator.config import Project
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)
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


def test_poll_once_reflects_label_transition_made_by_on_issues_fetched() -> None:
    """issue #97: on_issues_fetched内でオーケストレータ自身が行ったラベル遷移
    （コメント指示検知・クローズ検知を模したフェイク）が、同一poll_once呼び出しの
    aggregate()結果（プロジェクト状況）に反映されることを検証する。"""
    state_by_repo = {
        "nosetech/project-a": [_issue("nosetech/project-a", 1, [STATUS_TODO])],
    }

    def list_issues(repo: str) -> list[IssueSummary]:
        # 呼び出すたびに現在の状態ラベルを反映した最新のイシュー一覧を返す
        # （実際のgh CLI呼び出しと同様、都度GitHubから取得し直す想定）
        return [
            _issue(issue.repo, issue.number, list(issue.labels)) for issue in state_by_repo[repo]
        ]

    def on_issues_fetched(issues_by_repo: dict[str, list[IssueSummary]]) -> None:
        # コメント指示検知等によりオーケストレータ自身がラベルを書き換える処理を模す
        state_by_repo["nosetech/project-a"][0].labels = [STATUS_IN_PROGRESS]

    state = poll_once(
        [PROJECT_A],
        list_issues=list_issues,
        on_issues_fetched=on_issues_fetched,
    )

    assert [p.label for p in state.project_status] == [STATUS_IN_PROGRESS]


def test_poll_once_skips_refetch_when_on_issues_fetched_is_none() -> None:
    """`on_issues_fetched`が`None`の場合（`server._refresh_store`からの呼び出し等）は
    再取得せず、無駄なGitHub API呼び出しを避ける（issue #97）。"""
    call_count = 0

    def list_issues(repo: str) -> list[IssueSummary]:
        nonlocal call_count
        call_count += 1
        return []

    poll_once([PROJECT_A], list_issues=list_issues)

    assert call_count == 1


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
