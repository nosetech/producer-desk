"""利用リミット待ちの自動再開（issue #331）の単体テスト。

- 解除予定時刻の記述の絶対時刻化（`usage_store.parse_limit_reset_at`）
- マーカーの組み立て・抽出（`limit_wait`）
- 429到達時の失敗コメント（`agent_runner._build_failure_comment`）
- 自動再開のポーリング（`limit_watcher.process_limit_waiting_issues`）
- 判断待ち一覧への利用リミット待ち情報の付与（`aggregation.aggregate`）
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from orchestrator.agent_runner import LimitAutoResume, _build_failure_comment
from orchestrator.aggregation import IssueSummary, aggregate
from orchestrator.config import Project
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.instruct import NoLimitWaitError, handle_cancel_limit_wait
from orchestrator.labels import STATUS_IN_PROGRESS, STATUS_NEEDS_HUMAN_DECISION
from orchestrator.limit_wait import (
    LIMIT_WAIT_CANCEL_MARKER,
    build_limit_resume_message,
    build_limit_wait_marker,
    extract_limit_resume_attempt,
    extract_limit_wait_marker,
)
from orchestrator.limit_watcher import LIMIT_RESUME_GRACE, process_limit_waiting_issues
from orchestrator.usage_store import parse_limit_reset_at

TOKYO = ZoneInfo("Asia/Tokyo")
# JSTで 2026-11-27 10:15
RECORDED_AT = datetime(2026, 11, 27, 1, 15, tzinfo=UTC)


# --- parse_limit_reset_at -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 実ログで確認できた文言（時刻のみ）。記録時刻以降で最初のその時刻
        ("resets 1pm (Asia/Tokyo)", datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO)),
        ("resets 6:30pm (Asia/Tokyo)", datetime(2026, 11, 27, 18, 30, tzinfo=TOKYO)),
        ("resets 1:20pm (Asia/Tokyo)", datetime(2026, 11, 27, 13, 20, tzinfo=TOKYO)),
        # 記録時刻（10:15）より前の時刻は翌日
        ("resets 1am (Asia/Tokyo)", datetime(2026, 11, 28, 1, 0, tzinfo=TOKYO)),
        ("resets 10:15am (Asia/Tokyo)", datetime(2026, 11, 28, 10, 15, tzinfo=TOKYO)),
        ("resets 12am (Asia/Tokyo)", datetime(2026, 11, 28, 0, 0, tzinfo=TOKYO)),
        ("resets 12pm (Asia/Tokyo)", datetime(2026, 11, 27, 12, 0, tzinfo=TOKYO)),
        # CLI出力の全文からでも抽出できる
        (
            "You've hit your 5-hour limit · resets 1pm (Asia/Tokyo)",
            datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO),
        ),
        # 日付付き
        ("resets Nov 28, 3pm (Asia/Tokyo)", datetime(2026, 11, 28, 15, 0, tzinfo=TOKYO)),
        ("resets Nov 28 at 3pm (Asia/Tokyo)", datetime(2026, 11, 28, 15, 0, tzinfo=TOKYO)),
        # 年またぎ
        ("resets Jan 2, 9am (Asia/Tokyo)", datetime(2027, 1, 2, 9, 0, tzinfo=TOKYO)),
        # タイムゾーン無しはJST
        ("resets 3pm", datetime(2026, 11, 27, 15, 0, tzinfo=TOKYO)),
        ("resets 13:00", datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO)),
        # 別タイムゾーン
        (
            "resets 5pm (America/Los_Angeles)",
            datetime(2026, 11, 27, 17, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        ),
    ],
)
def test_parse_limit_reset_at_converts_to_absolute_time(text: str, expected: datetime) -> None:
    result = parse_limit_reset_at(text, RECORDED_AT)
    assert result == expected
    assert result is not None and result.tzinfo is not None


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "unexpected error",
        "resets soon",
        "resets 3 (Asia/Tokyo)",  # am/pmも分も無く判別できない
        "resets 13pm (Asia/Tokyo)",
        "resets 25:00",
        "resets 3pm (Not/AZone)",
        "resets Foo 28, 3pm",
        "resets Feb 30, 3pm",
    ],
)
def test_parse_limit_reset_at_returns_none_when_unparseable(text: str | None) -> None:
    assert parse_limit_reset_at(text, RECORDED_AT) is None


# --- markers -------------------------------------------------------------


def test_limit_wait_marker_round_trip() -> None:
    reset_at = datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO)
    marker = build_limit_wait_marker(reset_at, 2)
    wait = extract_limit_wait_marker(f"本文\n\n{marker}\n\n{BOT_COMMENT_MARKER}")
    assert wait is not None
    assert wait.reset_at == reset_at
    assert wait.attempt == 2


@pytest.mark.parametrize(
    "body",
    [
        None,
        "マーカーなし",
        "<!-- producer-desk:limit-wait\n{broken\n-->",
        '<!-- producer-desk:limit-wait\n{"reset_at": 1}\n-->',
        '<!-- producer-desk:limit-wait\n{"reset_at": "not-a-date"}\n-->',
        # タイムゾーン無しの時刻は受け付けない
        '<!-- producer-desk:limit-wait\n{"reset_at": "2026-11-27T13:00:00"}\n-->',
    ],
)
def test_extract_limit_wait_marker_ignores_invalid(body: str | None) -> None:
    assert extract_limit_wait_marker(body) is None


def test_limit_resume_attempt_round_trip() -> None:
    assert extract_limit_resume_attempt(build_limit_resume_message(2)) == 2
    assert extract_limit_resume_attempt("人間からの指示") == 0
    assert extract_limit_resume_attempt(None) == 0


# --- _build_failure_comment ---------------------------------------------


def _limit_payload(text: str = "You've hit your session limit · resets 1pm (Asia/Tokyo)") -> dict:
    return {"is_error": True, "api_error_status": 429, "result": text}


def test_failure_comment_includes_marker_when_reset_time_converted() -> None:
    comment = _build_failure_comment(
        _limit_payload(),
        returncode=1,
        log_path=Path("/tmp/x.log"),
        recorded_at=RECORDED_AT,
        auto_resume=LimitAutoResume(max_attempts=3),
    )
    assert "resets 1pm (Asia/Tokyo)" in comment
    assert "11/27 13:00" in comment
    wait = extract_limit_wait_marker(comment)
    assert wait is not None
    assert wait.reset_at == datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO)
    assert wait.attempt == 1


def test_failure_comment_carries_over_previous_attempt() -> None:
    comment = _build_failure_comment(
        _limit_payload(),
        returncode=1,
        log_path=Path("/tmp/x.log"),
        recorded_at=RECORDED_AT,
        auto_resume=LimitAutoResume(max_attempts=3, previous_attempt=2),
    )
    wait = extract_limit_wait_marker(comment)
    assert wait is not None and wait.attempt == 3


def test_failure_comment_stops_auto_resume_when_max_attempts_reached() -> None:
    comment = _build_failure_comment(
        _limit_payload(),
        returncode=1,
        log_path=Path("/tmp/x.log"),
        recorded_at=RECORDED_AT,
        auto_resume=LimitAutoResume(max_attempts=3, previous_attempt=3),
    )
    assert extract_limit_wait_marker(comment) is None
    assert "上限（3回）" in comment


def test_failure_comment_without_marker_when_unparseable_or_disabled() -> None:
    unparseable = _build_failure_comment(
        _limit_payload("You've hit your limit · resets soon"),
        returncode=1,
        log_path=Path("/tmp/x.log"),
        recorded_at=RECORDED_AT,
        auto_resume=LimitAutoResume(max_attempts=3),
    )
    assert extract_limit_wait_marker(unparseable) is None
    assert "API利用リミット" in unparseable

    disabled = _build_failure_comment(
        _limit_payload(),
        returncode=1,
        log_path=Path("/tmp/x.log"),
        recorded_at=RECORDED_AT,
        auto_resume=None,
    )
    assert extract_limit_wait_marker(disabled) is None
    assert disabled == (
        ":warning: Claude CodeのAPI利用リミットに達したため停止しました。"
        "（resets 1pm (Asia/Tokyo)）"
    )


def test_project_validates_limit_auto_resume_settings() -> None:
    project = Project(repo="o/r", worktree_path="/tmp/r")
    assert project.limit_auto_resume is True
    assert project.limit_auto_resume_max_attempts == 3
    with pytest.raises(ValueError):
        Project(repo="o/r", worktree_path="/tmp/r", limit_auto_resume="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Project(repo="o/r", worktree_path="/tmp/r", limit_auto_resume_max_attempts=0)


# --- limit_watcher ------------------------------------------------------

RESET_AT = datetime(2026, 11, 27, 13, 0, tzinfo=TOKYO)


def _wait_comment(attempt: int = 1) -> dict:
    return {
        "body": (
            ":warning: 利用リミット\n\n"
            f"{build_limit_wait_marker(RESET_AT, attempt)}\n\n{BOT_COMMENT_MARKER}"
        )
    }


def _issue(
    comments: list[dict], labels: list[str] | None = None, state: str = "OPEN"
) -> IssueSummary:
    return IssueSummary(
        repo="o/r",
        number=7,
        title="t",
        labels=labels if labels is not None else [STATUS_NEEDS_HUMAN_DECISION],
        comments=comments,
        updated_at="2026-11-27T00:00:00Z",
        state=state,
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


class FakeQueue:
    def __init__(self, active: bool = False) -> None:
        self.active = active
        self.enqueued: list[tuple[str, int, str]] = []

    def is_active(self, repo: str, issue_number: int) -> bool:
        return self.active

    def enqueue(self, repo: str, issue_number: int, message: str) -> None:
        self.enqueued.append((repo, issue_number, message))


def _run_watcher(
    issue: IssueSummary, *, now: datetime, queue: FakeQueue | None = None
) -> tuple[FakeLabels, FakeQueue]:
    labels = FakeLabels(set(issue.labels))
    queue = queue or FakeQueue()
    process_limit_waiting_issues(
        {"o/r": [issue]},
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        dispatch_queue=queue,  # type: ignore[arg-type]
        now=lambda: now,
    )
    return labels, queue


AFTER_RESET = RESET_AT + LIMIT_RESUME_GRACE + timedelta(seconds=1)


def test_watcher_resumes_after_reset_time() -> None:
    labels, queue = _run_watcher(_issue([_wait_comment(attempt=2)]), now=AFTER_RESET)
    assert labels.labels == {STATUS_IN_PROGRESS}
    assert len(queue.enqueued) == 1
    repo, number, message = queue.enqueued[0]
    assert (repo, number) == ("o/r", 7)
    # 連続回数を再開メッセージに引き継ぐ
    assert extract_limit_resume_attempt(message) == 2


def test_watcher_waits_until_reset_time_plus_grace() -> None:
    labels, queue = _run_watcher(
        _issue([_wait_comment()]), now=RESET_AT + LIMIT_RESUME_GRACE - timedelta(seconds=1)
    )
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert queue.enqueued == []


@pytest.mark.parametrize(
    "comments",
    [
        # マーカーの後に人間の返信・別モデル指定がある
        [_wait_comment(), {"body": "/model litellm:qwen\n\n再開してください"}],
        # 取り消しコメントがある
        [
            _wait_comment(),
            {"body": f"取り消し\n\n{LIMIT_WAIT_CANCEL_MARKER}\n\n{BOT_COMMENT_MARKER}"},
        ],
        # Bot投稿でない（人間がマーカーを書いた）
        [{"body": build_limit_wait_marker(RESET_AT, 1)}],
        [],
    ],
)
def test_watcher_skips_when_latest_comment_is_not_wait_marker(comments: list[dict]) -> None:
    labels, queue = _run_watcher(_issue(comments), now=AFTER_RESET)
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}
    assert queue.enqueued == []


def test_watcher_skips_non_decision_closed_and_active_issues() -> None:
    _, queue = _run_watcher(_issue([_wait_comment()], labels=[STATUS_IN_PROGRESS]), now=AFTER_RESET)
    assert queue.enqueued == []
    _, queue = _run_watcher(_issue([_wait_comment()], state="CLOSED"), now=AFTER_RESET)
    assert queue.enqueued == []
    labels, queue = _run_watcher(
        _issue([_wait_comment()]), now=AFTER_RESET, queue=FakeQueue(active=True)
    )
    assert queue.enqueued == []
    assert labels.labels == {STATUS_NEEDS_HUMAN_DECISION}


def test_watcher_swallows_gh_failure_and_retries_later() -> None:
    queue = FakeQueue()

    def failing_get_labels(repo: str, issue_number: int) -> set[str]:
        raise subprocess.CalledProcessError(1, ["gh"])

    process_limit_waiting_issues(
        {"o/r": [_issue([_wait_comment()])]},
        get_labels=failing_get_labels,
        add_label=lambda *a: None,
        remove_label=lambda *a: None,
        dispatch_queue=queue,  # type: ignore[arg-type]
        now=lambda: AFTER_RESET,
    )
    assert queue.enqueued == []


# --- aggregation / cancel -----------------------------------------------


def test_aggregate_attaches_limit_wait_to_decisions() -> None:
    waiting = _issue([_wait_comment(attempt=2)])
    plain = IssueSummary(
        repo="o/r",
        number=8,
        title="t",
        labels=[STATUS_NEEDS_HUMAN_DECISION],
        comments=[{"body": "質問です"}],
        updated_at="2026-11-26T00:00:00Z",
    )
    state = aggregate({"o/r": [waiting, plain]})
    by_number = {issue.number: issue for issue in state.decisions}
    info = by_number[7].limit_wait
    assert info is not None
    assert info.reset_at == RESET_AT.isoformat()
    assert info.attempt == 2
    assert by_number[8].limit_wait is None


def test_cancel_limit_wait_posts_cancel_marker() -> None:
    posted: list[tuple[str, int, str]] = []
    handle_cancel_limit_wait(
        _issue([_wait_comment()]),
        post_comment=lambda repo, number, body: posted.append((repo, number, body)),
    )
    assert len(posted) == 1
    assert LIMIT_WAIT_CANCEL_MARKER in posted[0][2]


def test_cancel_limit_wait_rejects_issue_without_marker() -> None:
    with pytest.raises(NoLimitWaitError):
        handle_cancel_limit_wait(_issue([{"body": "質問です"}]), post_comment=lambda *a: None)
