"""orchestrator.server の単体テスト。実際にループバックでHTTPリクエストを送って検証する。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from orchestrator.aggregation import ActivityEvent, AggregatedState, IssueSummary
from orchestrator.config import Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)
from orchestrator.server import StateStore, make_server
from orchestrator.usage_store import DailyModelUsage, LimitStatus

PROJECT_A = Project(repo="nosetech/project-a", worktree_path="/tmp/project-a")


class FakeLabels:
    def __init__(self, initial: dict[int, set[str]] | None = None) -> None:
        self.labels_by_issue: dict[int, set[str]] = initial or {}

    def get_labels(self, repo: str, issue_number: int) -> set[str]:
        return set(self.labels_by_issue.get(issue_number, set()))

    def add_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels_by_issue.setdefault(issue_number, set()).add(label)

    def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        self.labels_by_issue.setdefault(issue_number, set()).discard(label)


class FakeComments:
    def __init__(self) -> None:
        self.posted: list[tuple[str, int, str]] = []

    def post_comment(self, repo: str, issue_number: int, body: str) -> None:
        self.posted.append((repo, issue_number, body))


class FakeReviewMerge:
    def __init__(self, pr_number: int | None) -> None:
        self.pr_number = pr_number
        self.merge_calls: list[tuple[str, int]] = []
        self.close_calls: list[tuple[str, int]] = []

    def resolve_pr_number(self, repo: str, issue_number: int) -> int | None:
        return self.pr_number

    def merge_pr(self, repo: str, pr_number: int) -> None:
        self.merge_calls.append((repo, pr_number))

    def close_issue(self, repo: str, issue_number: int) -> None:
        self.close_calls.append((repo, issue_number))


class FakeIssueCreator:
    def __init__(self, start_number: int = 100) -> None:
        self._next = start_number
        self.created: list[tuple[str, str, str]] = []

    def create_issue(self, repo: str, title: str, body: str) -> int:
        self.created.append((repo, title, body))
        number = self._next
        self._next += 1
        return number


def _recording_dispatch_queue() -> tuple[
    DispatchQueue, list[tuple[str, int, str]], threading.Event
]:
    calls: list[tuple[str, int, str]] = []
    event = threading.Event()

    def dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        calls.append((repo, issue_number, message))
        event.set()

    return DispatchQueue(dispatch_fn=dispatch_fn), calls, event


def _run_server(store: StateStore, **kwargs) -> tuple:
    server = make_server(store, host="127.0.0.1", port=0, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path: str) -> tuple[int, dict]:
    host, port = server.server_address[0], server.server_address[1]
    with urllib.request.urlopen(f"http://{host}:{port}{path}") as response:
        return response.status, json.loads(response.read())


def _post(server, path: str, payload: dict) -> tuple[int, dict]:
    host, port = server.server_address[0], server.server_address[1]
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_state_store_returns_none_before_any_update() -> None:
    store = StateStore()

    assert store.get() is None


def test_state_store_returns_latest_set_state() -> None:
    store = StateStore()
    state = AggregatedState(decisions=[], activity=[])

    store.set(state)

    assert store.get() is state


def test_get_api_state_returns_empty_lists_before_first_poll() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, body = _get(server, "/api/state")
        assert status == 200
        assert body == {"decisions": [], "reviews": [], "activity": []}
    finally:
        server.shutdown()


def test_get_api_state_returns_latest_aggregated_state() -> None:
    store = StateStore()
    store.set(
        AggregatedState(
            decisions=[
                IssueSummary(
                    repo="nosetech/project-a",
                    number=1,
                    title="t",
                    labels=["needs-human-decision"],
                    comments=[],
                    updated_at="2026-08-01T00:00:00Z",
                )
            ],
            activity=[
                ActivityEvent(
                    repo="nosetech/project-a",
                    number=1,
                    title="t",
                    label="needs-human-decision",
                    updated_at="2026-08-01T00:00:00Z",
                )
            ],
        )
    )
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, body = _get(server, "/api/state")
        assert status == 200
        assert body["decisions"][0]["number"] == 1
        assert body["activity"][0]["label"] == "needs-human-decision"
    finally:
        server.shutdown()


def test_get_api_usage_returns_daily_usage_and_no_current_limit() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    daily = [
        DailyModelUsage(
            date="2026-08-09",
            model="claude-sonnet-5",
            input_tokens=1000,
            output_tokens=200,
            total_cost_usd=0.5,
        ),
        DailyModelUsage(
            date="2026-08-09",
            model="deepseek-coder-v2:16b",
            input_tokens=3000,
            output_tokens=800,
            total_cost_usd=0.0,
        ),
    ]
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        daily_model_usage=lambda: daily,
        current_limit_status=lambda: None,
    )
    try:
        status, body = _get(server, "/api/usage")
        assert status == 200
        assert body["currentLimit"] is None
        assert body["daily"] == [
            {
                "date": "2026-08-09",
                "model": "claude-sonnet-5",
                "input_tokens": 1000,
                "output_tokens": 200,
                "total_cost_usd": 0.5,
            },
            {
                "date": "2026-08-09",
                "model": "deepseek-coder-v2:16b",
                "input_tokens": 3000,
                "output_tokens": 800,
                "total_cost_usd": 0.0,
            },
        ]
    finally:
        server.shutdown()


def test_get_api_usage_returns_current_limit_status_when_present() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    limit_status = LimitStatus(
        repo="nosetech/project-a",
        issue_number=12,
        recorded_at="2026-08-09T04:00:00+00:00",
        api_error_status=429,
        error_message="You've hit your session limit · resets 1pm (Asia/Tokyo)",
        reset_at_text="resets 1pm (Asia/Tokyo)",
    )
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        daily_model_usage=lambda: [],
        current_limit_status=lambda: limit_status,
    )
    try:
        status, body = _get(server, "/api/usage")
        assert status == 200
        assert body["currentLimit"]["repo"] == "nosetech/project-a"
        assert body["currentLimit"]["reset_at_text"] == "resets 1pm (Asia/Tokyo)"
    finally:
        server.shutdown()


def test_unknown_path_returns_404() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, _ = _post(server, "/unknown", {})
        assert status == 404
    finally:
        server.shutdown()


def test_instruct_approve_posts_comment_transitions_label_and_dispatches() -> None:
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    dispatch_queue, calls, event = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["label"] == STATUS_IN_PROGRESS
        assert body["dispatched"] is True
        assert comments.posted == [("nosetech/project-a", 1, "承認します。進めてください。")]
        assert labels.labels_by_issue[1] == {STATUS_IN_PROGRESS}
        assert event.wait(timeout=2)
        assert calls == [("nosetech/project-a", 1, "承認します。進めてください。")]
    finally:
        server.shutdown()


def test_instruct_reject_action_no_longer_supported() -> None:
    """rejectは設計から廃止済み（docs/basic-design.md 2-3、issue #55）。

    未知のactionと同様に400を返すことを保証し、意図せず復活しないようにする。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    dispatch_queue, calls, _ = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
    )
    try:
        status, body = _post(
            server,
            "/api/projects/nosetech/project-a/issues/1/instruct",
            {"action": "reject", "message": "設計を見直してください"},
        )

        assert status == 400
        assert "error" in body
        assert comments.posted == []
        assert labels.labels_by_issue[1] == {STATUS_NEEDS_HUMAN_DECISION}
        assert calls == []
    finally:
        server.shutdown()


def test_instruct_approve_on_in_review_merges_pr_and_skips_comment_and_dispatch() -> None:
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33)
    dispatch_queue, calls, _ = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["dispatched"] is False
        assert review_merge.merge_calls == [("nosetech/project-a", 33)]
        assert review_merge.close_calls == [("nosetech/project-a", 1)]
        assert comments.posted == []
        assert labels.labels_by_issue[1] == {STATUS_IN_REVIEW}
        assert calls == []
    finally:
        server.shutdown()


def test_instruct_approve_on_in_review_without_linked_pr_returns_502() -> None:
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=None)
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        resolve_pr_number=review_merge.resolve_pr_number,
        merge_pr=review_merge.merge_pr,
        close_issue=review_merge.close_issue,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 502
        assert "error" in body
        assert review_merge.merge_calls == []
        assert review_merge.close_calls == []
    finally:
        server.shutdown()


def test_instruct_missing_action_returns_400() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, _ = _post(server, "/api/projects/nosetech/project-a/issues/1/instruct", {})
        assert status == 400
    finally:
        server.shutdown()


def test_instruct_unknown_repo_returns_404() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, _ = _post(
            server, "/api/projects/nosetech/unknown-repo/issues/1/instruct", {"action": "approve"}
        )
        assert status == 404
    finally:
        server.shutdown()


def test_create_issue_immediate_dispatch() -> None:
    store = StateStore()
    labels = FakeLabels()
    issue_creator = FakeIssueCreator(start_number=42)
    dispatch_queue, calls, event = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        create_issue=issue_creator.create_issue,
    )
    try:
        status, body = _post(
            server,
            "/api/projects/nosetech/project-a/issues",
            {"title": "新機能", "prompt": "実装してください", "dispatch": "immediate"},
        )

        assert status == 201
        assert body["issue_number"] == 42
        assert body["dispatched"] is True
        assert issue_creator.created == [("nosetech/project-a", "新機能", "実装してください")]
        assert labels.labels_by_issue[42] == {STATUS_IN_PROGRESS}
        assert event.wait(timeout=2)
        assert calls == [("nosetech/project-a", 42, "実装してください")]
    finally:
        server.shutdown()


def test_create_issue_queued_does_not_dispatch() -> None:
    store = StateStore()
    labels = FakeLabels()
    issue_creator = FakeIssueCreator(start_number=42)
    dispatch_queue, calls, _ = _recording_dispatch_queue()
    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        create_issue=issue_creator.create_issue,
    )
    try:
        status, body = _post(
            server,
            "/api/projects/nosetech/project-a/issues",
            {"title": "新機能", "prompt": "実装してください", "dispatch": "queued"},
        )

        assert status == 201
        assert body["dispatched"] is False
        assert labels.labels_by_issue[42] == {STATUS_TODO}
        assert calls == []
    finally:
        server.shutdown()


def test_create_issue_invalid_dispatch_value_returns_400() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, _ = _post(
            server,
            "/api/projects/nosetech/project-a/issues",
            {"title": "t", "prompt": "p", "dispatch": "later"},
        )
        assert status == 400
    finally:
        server.shutdown()
