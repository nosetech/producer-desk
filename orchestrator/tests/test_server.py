"""orchestrator.server の単体テスト。実際にループバックでHTTPリクエストを送って検証する。"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request

from orchestrator.aggregation import STATUS_COUNT_KEYS, AggregatedState, IssueSummary, ProjectStatus
from orchestrator.config import Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)
from orchestrator.server import ProgressStore, StateStore, make_server
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
    def __init__(self, pr_number: int | None, *, branch: str = "feature/issue-1-something") -> None:
        self.pr_number = pr_number
        self.branch = branch
        self.merge_calls: list[tuple[str, int]] = []
        self.close_calls: list[tuple[str, int]] = []
        self.get_pr_branch_calls: list[tuple[str, int]] = []
        self.delete_branch_calls: list[tuple[str, str]] = []
        self.sync_worktree_calls: list[tuple[str, str]] = []

    def resolve_pr_number(self, repo: str, issue_number: int) -> int | None:
        return self.pr_number

    def merge_pr(self, repo: str, pr_number: int) -> None:
        self.merge_calls.append((repo, pr_number))

    def close_issue(self, repo: str, issue_number: int) -> None:
        self.close_calls.append((repo, issue_number))

    def get_pr_branch(self, repo: str, pr_number: int) -> str:
        self.get_pr_branch_calls.append((repo, pr_number))
        return self.branch

    def delete_branch(self, repo: str, branch: str) -> None:
        self.delete_branch_calls.append((repo, branch))

    def sync_worktree(self, worktree_path: str, branch: str) -> None:
        self.sync_worktree_calls.append((worktree_path, branch))


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
    # list_issuesを指定しないテストは、instruct/create_issue成功後の同期state再取得
    # （issue #70）で実際の`gh`コマンドを叩かないよう、空リストを返すフェイクを既定にする。
    kwargs.setdefault("list_issues", lambda repo: [])
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
    state = AggregatedState(decisions=[], project_status=[])

    store.set(state)

    assert store.get() is state


def test_get_api_state_returns_empty_lists_before_first_poll() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, body = _get(server, "/api/state")
        assert status == 200
        assert body == {
            "decisions": [],
            "reviews": [],
            "project_status": [],
            "status_counts": dict.fromkeys(STATUS_COUNT_KEYS, 0),
        }
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
            project_status=[
                ProjectStatus(
                    repo="nosetech/project-a",
                    label="needs-human-decision",
                    number=1,
                    title="t",
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
        assert body["project_status"][0]["label"] == "needs-human-decision"
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


def test_progress_store_set_get_clear() -> None:
    progress = ProgressStore()

    assert progress.get("abc") is None

    progress.set("abc", "comment")
    assert progress.get("abc") == "comment"

    progress.set("abc", "label")
    assert progress.get("abc") == "label"

    progress.clear("abc")
    assert progress.get("abc") is None


def test_get_api_progress_returns_null_stage_for_unknown_id() -> None:
    store = StateStore()
    dispatch_queue, _, _ = _recording_dispatch_queue()
    server, _ = _run_server(store, projects=[PROJECT_A], dispatch_queue=dispatch_queue)
    try:
        status, body = _get(server, "/api/progress/does-not-exist")

        assert status == 200
        assert body == {"stage": None}
    finally:
        server.shutdown()


def test_instruct_progress_reports_stage_while_in_flight_and_clears_after() -> None:
    """段階表示（ComposerBar）向けの/api/progressが、処理中の実際の段階を反映し、
    完了後は破棄されることを検証する（擬似進行ではなくon_stageコールバック経由）。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_TODO}})
    comments = FakeComments()
    dispatch_queue, _, event = _recording_dispatch_queue()
    release_label_step = threading.Event()

    def blocking_get_labels(repo: str, issue_number: int) -> set[str]:
        release_label_step.wait(timeout=2)
        return labels.get_labels(repo, issue_number)

    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=blocking_get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
    )
    try:
        responses: dict[str, tuple[int, dict]] = {}

        def do_post() -> None:
            responses["result"] = _post(
                server,
                "/api/projects/nosetech/project-a/issues/1/instruct",
                {"action": "instruct", "message": "進めて", "progressId": "req-1"},
            )

        poster = threading.Thread(target=do_post)
        poster.start()
        try:
            deadline = time.monotonic() + 2
            stage = None
            while time.monotonic() < deadline:
                _, body = _get(server, "/api/progress/req-1")
                stage = body["stage"]
                if stage == "comment":
                    break
                time.sleep(0.01)
            assert stage == "comment", "post_comment直後の段階がポーリングで観測できない"
        finally:
            release_label_step.set()
            poster.join(timeout=2)

        status, _ = responses["result"]
        assert status == 200
        assert event.wait(timeout=2)

        _, body = _get(server, "/api/progress/req-1")
        assert body == {"stage": None}
    finally:
        server.shutdown()


def test_create_issue_progress_reports_stage_while_in_flight_and_clears_after() -> None:
    store = StateStore()
    labels = FakeLabels()
    issue_creator = FakeIssueCreator()
    dispatch_queue, _, event = _recording_dispatch_queue()
    release_add_label = threading.Event()

    def blocking_add_label(repo: str, issue_number: int, label: str) -> None:
        release_add_label.wait(timeout=2)
        labels.add_label(repo, issue_number, label)

    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=blocking_add_label,
        remove_label=labels.remove_label,
        create_issue=issue_creator.create_issue,
    )
    try:
        responses: dict[str, tuple[int, dict]] = {}

        def do_post() -> None:
            responses["result"] = _post(
                server,
                "/api/projects/nosetech/project-a/issues",
                {
                    "title": "新機能",
                    "prompt": "プロンプト本文",
                    "dispatch": "immediate",
                    "progressId": "req-2",
                },
            )

        poster = threading.Thread(target=do_post)
        poster.start()
        try:
            deadline = time.monotonic() + 2
            stage = None
            while time.monotonic() < deadline:
                _, body = _get(server, "/api/progress/req-2")
                stage = body["stage"]
                if stage == "issue":
                    break
                time.sleep(0.01)
            assert stage == "issue", "issue作成直後の段階がポーリングで観測できない"
        finally:
            release_add_label.set()
            poster.join(timeout=2)

        status, _ = responses["result"]
        assert status == 201
        assert event.wait(timeout=2)

        _, body = _get(server, "/api/progress/req-2")
        assert body == {"stage": None}
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


def test_instruct_approve_refreshes_store_synchronously() -> None:
    """instruct成功直後にStateStoreが最新化され、5分間隔の背景ポーリングを待たない（issue #70）。"""
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    dispatch_queue, _, event = _recording_dispatch_queue()

    def list_issues(repo: str) -> list[IssueSummary]:
        return [
            IssueSummary(
                repo=repo,
                number=2,
                title="次の判断待ち",
                labels=[STATUS_NEEDS_HUMAN_DECISION],
                comments=[],
                updated_at="2026-08-10T00:00:00Z",
            )
        ]

    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        list_issues=list_issues,
    )
    try:
        assert store.get() is None

        status, _ = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert event.wait(timeout=2)
        state = store.get()
        assert state is not None
        assert [d.number for d in state.decisions] == [2]
    finally:
        server.shutdown()


def test_instruct_approve_on_in_review_refreshes_store_synchronously() -> None:
    """承認直後の同期state再取得時点で、レビュー待ち一覧からカードが消えている必要がある。

    `list_issues`をラベルの実際の状態と連動させることで、`status:in-review`ラベルを
    `status:closed`へ遷移させ忘れると（=マージ・クローズはするがラベルを変えないと）
    このテストが失敗する回帰テストになっている（issue #70フォローアップ）。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")
    dispatch_queue, _, _ = _recording_dispatch_queue()

    def list_issues(repo: str) -> list[IssueSummary]:
        return [
            IssueSummary(
                repo=repo,
                number=1,
                title="レビュー待ちissue",
                labels=sorted(labels.labels_by_issue.get(1, set())),
                comments=[],
                updated_at="2026-08-10T00:00:00Z",
            )
        ]

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
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=review_merge.sync_worktree,
        list_issues=list_issues,
    )
    try:
        status, _ = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        state = store.get()
        assert state is not None
        assert state.reviews == []
        assert review_merge.sync_worktree_calls == [
            (PROJECT_A.worktree_path, "feature/issue-1-something")
        ]
    finally:
        server.shutdown()


def test_instruct_approve_returns_200_even_if_store_refresh_fails() -> None:
    """state再取得の失敗は、既に成功している指示操作のレスポンスを損なわない（issue #70）。

    再取得はログ警告に留め、最新化は次回の背景ポーリング（5分間隔）に委ねる。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    dispatch_queue, _, event = _recording_dispatch_queue()

    def failing_list_issues(repo: str) -> list[IssueSummary]:
        raise subprocess.CalledProcessError(1, ["gh", "issue", "list"])

    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        post_comment=comments.post_comment,
        list_issues=failing_list_issues,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["label"] == STATUS_IN_PROGRESS
        assert store.get() is None
        assert event.wait(timeout=2)
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
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")
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
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=review_merge.sync_worktree,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["dispatched"] is False
        assert review_merge.merge_calls == [("nosetech/project-a", 33)]
        assert review_merge.close_calls == [("nosetech/project-a", 1)]
        assert review_merge.get_pr_branch_calls == [("nosetech/project-a", 33)]
        assert review_merge.delete_branch_calls == [
            ("nosetech/project-a", "feature/issue-1-something")
        ]
        assert comments.posted == []
        assert labels.labels_by_issue[1] == {STATUS_CLOSED}
        assert calls == []
        assert review_merge.sync_worktree_calls == [
            (PROJECT_A.worktree_path, "feature/issue-1-something")
        ]
    finally:
        server.shutdown()


def test_instruct_concurrent_requests_to_same_issue_are_rejected_with_409() -> None:
    """同一issueへの同時approve/instructリクエストは片方が409で拒否される（issue #111）。

    `status:in-review`への`approve`は`dispatch_queue`を経由せずPRマージ・issueクローズを
    同期的に直接実行するため、処理中に同一issueへの後続リクエストが割り込むと、
    ラベル遷移やコメント投稿が競合しうる。in-flightロックにより後続は409になる。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")

    started_event = threading.Event()
    release_event = threading.Event()

    def blocking_merge_pr(repo: str, pr_number: int) -> None:
        started_event.set()
        release_event.wait(timeout=2)
        review_merge.merge_pr(repo, pr_number)

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
        merge_pr=blocking_merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=review_merge.sync_worktree,
    )

    first_result: list[tuple[int, dict]] = []

    def do_first_request() -> None:
        first_result.append(
            _post(
                server,
                "/api/projects/nosetech/project-a/issues/1/instruct",
                {"action": "approve"},
            )
        )

    first_thread = threading.Thread(target=do_first_request)
    first_thread.start()
    try:
        assert started_event.wait(timeout=2)

        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 409
        assert "error" in body
    finally:
        release_event.set()
        first_thread.join(timeout=2)
        server.shutdown()

    assert first_result[0][0] == 200


def test_instruct_concurrent_requests_to_different_issues_are_not_blocked() -> None:
    """ロックはrepo+issue_number単位であり、別issueへの同時リクエストはブロックしない
    （issue #111）。"""
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}, 2: {STATUS_NEEDS_HUMAN_DECISION}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")

    started_event = threading.Event()
    release_event = threading.Event()

    def blocking_merge_pr(repo: str, pr_number: int) -> None:
        started_event.set()
        release_event.wait(timeout=2)
        review_merge.merge_pr(repo, pr_number)

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
        merge_pr=blocking_merge_pr,
        close_issue=review_merge.close_issue,
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=review_merge.sync_worktree,
    )

    first_thread = threading.Thread(
        target=lambda: _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )
    )
    first_thread.start()
    try:
        assert started_event.wait(timeout=2)

        status, _ = _post(
            server, "/api/projects/nosetech/project-a/issues/2/instruct", {"action": "approve"}
        )

        assert status == 200
    finally:
        release_event.set()
        first_thread.join(timeout=2)
        server.shutdown()


def test_instruct_approve_on_in_review_skips_worktree_sync_when_dispatch_running() -> None:
    """同じプロジェクトの別issueでAgent Runnerが実行中の場合、worktree同期をスキップする。

    実行中にworktreeを横から`git checkout`すると、実行中セッションの作業ディレクトリを
    書き換えてしまうため（issue #80）。
    """
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")

    release_event = threading.Event()
    started_event = threading.Event()

    def blocking_dispatch_fn(repo: str, issue_number: int, message: str) -> None:
        started_event.set()
        release_event.wait(timeout=2)

    dispatch_queue = DispatchQueue(dispatch_fn=blocking_dispatch_fn)
    dispatch_queue.enqueue("nosetech/project-a", 2, "別issueが実行中")
    assert started_event.wait(timeout=2)

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
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=review_merge.delete_branch,
        sync_worktree=review_merge.sync_worktree,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["dispatched"] is False
        assert review_merge.delete_branch_calls == [
            ("nosetech/project-a", "feature/issue-1-something")
        ]
        assert review_merge.sync_worktree_calls == []
    finally:
        release_event.set()
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


def test_instruct_approve_on_in_review_returns_200_even_if_branch_deletion_fails() -> None:
    """ブランチ削除の失敗はマージ・issueクローズの成功に影響しない（issue #72）。"""
    store = StateStore()
    labels = FakeLabels(initial={1: {STATUS_IN_REVIEW}})
    comments = FakeComments()
    review_merge = FakeReviewMerge(pr_number=33, branch="feature/issue-1-something")

    def failing_delete_branch(repo: str, branch: str) -> None:
        review_merge.delete_branch_calls.append((repo, branch))
        raise subprocess.CalledProcessError(1, ["gh", "api"])

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
        get_pr_branch=review_merge.get_pr_branch,
        delete_branch=failing_delete_branch,
        sync_worktree=review_merge.sync_worktree,
    )
    try:
        status, body = _post(
            server, "/api/projects/nosetech/project-a/issues/1/instruct", {"action": "approve"}
        )

        assert status == 200
        assert body["dispatched"] is False
        assert review_merge.merge_calls == [("nosetech/project-a", 33)]
        assert review_merge.close_calls == [("nosetech/project-a", 1)]
        assert review_merge.delete_branch_calls == [
            ("nosetech/project-a", "feature/issue-1-something")
        ]
        assert calls == []
        assert review_merge.sync_worktree_calls == []
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


def test_create_issue_refreshes_store_synchronously() -> None:
    """create_issue成功直後にもStateStoreが最新化される（issue #70）。"""
    store = StateStore()
    labels = FakeLabels()
    issue_creator = FakeIssueCreator(start_number=42)
    dispatch_queue, _, event = _recording_dispatch_queue()

    def list_issues(repo: str) -> list[IssueSummary]:
        return [
            IssueSummary(
                repo=repo,
                number=42,
                title="新機能",
                labels=[STATUS_IN_PROGRESS],
                comments=[],
                updated_at="2026-08-10T00:00:00Z",
            )
        ]

    server, _ = _run_server(
        store,
        projects=[PROJECT_A],
        dispatch_queue=dispatch_queue,
        get_labels=labels.get_labels,
        add_label=labels.add_label,
        remove_label=labels.remove_label,
        create_issue=issue_creator.create_issue,
        list_issues=list_issues,
    )
    try:
        status, _ = _post(
            server,
            "/api/projects/nosetech/project-a/issues",
            {"title": "新機能", "prompt": "実装してください", "dispatch": "immediate"},
        )

        assert status == 201
        assert event.wait(timeout=2)
        state = store.get()
        assert state is not None
        assert [p.number for p in state.project_status] == [42]
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
