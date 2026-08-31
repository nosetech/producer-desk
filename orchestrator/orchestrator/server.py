"""ダッシュボード（Next.js）とオーケストレータ間の内部API。

仕様:
- docs/basic-design.md 2-2（GET /api/state、ダッシュボード表示用の集約データ提供。
  instruct/create_issue成功時のStateStore同期更新を含む）
- docs/basic-design.md 2-3（指示出しAPI: POST /api/projects/{repo}/issues/{issue_number}/instruct
  と POST /api/projects/{repo}/issues）
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orchestrator.aggregation import STATUS_COUNT_KEYS, AggregatedState
from orchestrator.config import Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import (
    CloseIssueFn,
    CreateIssueFn,
    DeleteBranchFn,
    GetPrBranchFn,
    MergePrFn,
    PostCommentFn,
    ResolvePrNumberFn,
)
from orchestrator.github_client import close_issue as gh_close_issue
from orchestrator.github_client import create_issue as gh_create_issue
from orchestrator.github_client import delete_branch as gh_delete_branch
from orchestrator.github_client import get_pr_branch as gh_get_pr_branch
from orchestrator.github_client import list_issues as gh_list_issues
from orchestrator.github_client import merge_pr as gh_merge_pr
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.github_client import resolve_pr_number as gh_resolve_pr_number
from orchestrator.instruct import ReviewMergeError, handle_create_issue, handle_instruct
from orchestrator.labels import (
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    gh_add_label,
    gh_get_labels,
    gh_remove_label,
)
from orchestrator.polling import ListIssuesFn, poll_once
from orchestrator.usage_store import DailyModelUsage, LimitStatus
from orchestrator.usage_store import current_limit_status as store_current_limit_status
from orchestrator.usage_store import daily_model_usage as store_daily_model_usage
from orchestrator.worktree import SyncWorktreeFn
from orchestrator.worktree import sync_worktree_after_branch_delete as gh_sync_worktree

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

INSTRUCT_PATH = re.compile(
    r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues/(?P<issue_number>\d+)/instruct$"
)
CREATE_ISSUE_PATH = re.compile(r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues$")
PROGRESS_PATH = re.compile(r"^/api/progress/(?P<progress_id>[^/]+)$")

DailyModelUsageFn = Callable[..., list[DailyModelUsage]]
CurrentLimitStatusFn = Callable[..., LimitStatus | None]

logger = logging.getLogger(__name__)


class StateStore:
    """最新の集約結果をスレッドセーフに保持する。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: AggregatedState | None = None

    def set(self, state: AggregatedState) -> None:
        with self._lock:
            self._state = state

    def get(self) -> AggregatedState | None:
        with self._lock:
            return self._state


class InstructInFlightLocks:
    """repo+issue_number単位のin-flightロック（issue #111）。

    `status:in-review`への`approve`は`dispatch_queue`を経由せずPRマージ・issueクローズを
    同期的に直接実行するため、同一issueへの`approve`/`instruct`がほぼ同時に届くと
    ラベル遷移やコメント投稿が競合しうる。`ThreadingHTTPServer`はリクエストごとに別スレッドで
    処理するため、`_handle_instruct`の処理中は該当issueへの後続リクエストを単純に拒否する
    ことで排他制御する（複数タブ・複数端末からの同時操作を想定。CLAUDE.md参照）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: set[tuple[str, int]] = set()

    def try_acquire(self, repo: str, issue_number: int) -> bool:
        with self._lock:
            key = (repo, issue_number)
            if key in self._in_flight:
                return False
            self._in_flight.add(key)
            return True

    def release(self, repo: str, issue_number: int) -> None:
        with self._lock:
            self._in_flight.discard((repo, issue_number))


class ProgressStore:
    """指示送信中の段階（"comment"/"label"/"issue"/"dispatch"）をprogress_id単位で保持する。

    ダッシュボードの段階表示（ComposerBar）向け。POSTリクエストは
    `instruct.py`のhandle_instruct/handle_create_issueを1リクエストの中で同期的に
    最後まで実行し、途中経過を応答として返さない。`ThreadingHTTPServer`はリクエスト
    ごとに別スレッドで動くため、その処理中に短間隔のGETポーリング（/api/progress/
    {progress_id}）で参照できるよう、on_stageコールバックの呼び出し時点の値を
    ここに書き込む。POSTが完了（成功/失敗いずれも）した時点でエントリを破棄する。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stages: dict[str, str] = {}

    def set(self, progress_id: str, stage: str) -> None:
        with self._lock:
            self._stages[progress_id] = stage

    def get(self, progress_id: str) -> str | None:
        with self._lock:
            return self._stages.get(progress_id)

    def clear(self, progress_id: str) -> None:
        with self._lock:
            self._stages.pop(progress_id, None)


def _make_handler(
    store: StateStore,
    *,
    projects: list[Project],
    known_repos: set[str],
    dispatch_queue: DispatchQueue,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    post_comment: PostCommentFn,
    create_issue: CreateIssueFn,
    daily_model_usage: DailyModelUsageFn,
    current_limit_status: CurrentLimitStatusFn,
    resolve_pr_number: ResolvePrNumberFn,
    merge_pr: MergePrFn,
    close_issue: CloseIssueFn,
    get_pr_branch: GetPrBranchFn,
    delete_branch: DeleteBranchFn,
    list_issues: ListIssuesFn,
    sync_worktree: SyncWorktreeFn,
) -> type[BaseHTTPRequestHandler]:
    projects_by_repo = {project.repo: project for project in projects}
    instruct_locks = InstructInFlightLocks()
    progress_store = ProgressStore()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # アクセスログはoff（オーケストレータ本体のログ設計は別issue）

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw)

        def _refresh_store(self) -> None:
            """instruct/create_issue成功直後にStateStoreを同期更新する（issue #70）。

            バックグラウンドポーリング（5分間隔）を待たずダッシュボードの再取得
            （GET /api/state）に最新状態を反映させ、カードが消えないまま二重操作
            できてしまう不具合を防ぐ。再取得自体の失敗は指示操作の成功を損なわないよう
            ログ警告に留め、次回のバックグラウンドポーリングでの復旧に委ねる。
            """
            try:
                state = poll_once(
                    projects,
                    list_issues=list_issues,
                    resolve_pr_number=resolve_pr_number,
                    is_dispatch_active=dispatch_queue.is_active,
                )
            except subprocess.CalledProcessError as e:
                logger.warning("instruct成功後のstate再取得に失敗しました: %s", e)
                return
            store.set(state)

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandlerのインターフェースに合わせる)
            if self.path == "/api/state":
                self._handle_state()
                return
            if self.path == "/api/usage":
                self._handle_usage()
                return

            progress_match = PROGRESS_PATH.match(self.path)
            if progress_match:
                self._handle_progress(progress_match.group("progress_id"))
                return

            self.send_response(404)
            self.end_headers()

        def _handle_progress(self, progress_id: str) -> None:
            self._send_json(200, {"stage": progress_store.get(progress_id)})

        def _handle_state(self) -> None:
            state = store.get()
            self._send_json(
                200,
                dataclasses.asdict(state)
                if state is not None
                else {
                    "decisions": [],
                    "reviews": [],
                    "project_status": [],
                    "status_counts": dict.fromkeys(STATUS_COUNT_KEYS, 0),
                },
            )

        def _handle_usage(self) -> None:
            limit_status = current_limit_status()
            self._send_json(
                200,
                {
                    "daily": [dataclasses.asdict(record) for record in daily_model_usage()],
                    "currentLimit": dataclasses.asdict(limit_status)
                    if limit_status is not None
                    else None,
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            instruct_match = INSTRUCT_PATH.match(self.path)
            if instruct_match:
                self._handle_instruct(
                    instruct_match.group("repo"), int(instruct_match.group("issue_number"))
                )
                return

            create_issue_match = CREATE_ISSUE_PATH.match(self.path)
            if create_issue_match:
                self._handle_create_issue(create_issue_match.group("repo"))
                return

            self._send_json(404, {"error": "not found"})

        def _handle_instruct(self, repo: str, issue_number: int) -> None:
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return

            if not instruct_locks.try_acquire(repo, issue_number):
                message = f"{repo}#{issue_number} は他の操作を処理中です。しばらくお待ちください"
                self._send_json(409, {"error": message})
                return

            progress_id: str | None = None
            try:
                try:
                    payload = self._read_json_body()
                    progress_id = payload.get("progressId")
                    on_stage = (
                        (lambda stage: progress_store.set(progress_id, stage))
                        if progress_id
                        else (lambda _stage: None)
                    )
                    result = handle_instruct(
                        repo,
                        issue_number,
                        payload["action"],
                        payload.get("message"),
                        get_labels=get_labels,
                        add_label=add_label,
                        remove_label=remove_label,
                        post_comment=post_comment,
                        dispatch_queue=dispatch_queue,
                        resolve_pr_number=resolve_pr_number,
                        merge_pr=merge_pr,
                        close_issue=close_issue,
                        get_pr_branch=get_pr_branch,
                        delete_branch=delete_branch,
                        worktree_path=projects_by_repo[repo].worktree_path,
                        sync_worktree=sync_worktree,
                        on_stage=on_stage,
                    )
                except (KeyError, ValueError) as e:
                    self._send_json(400, {"error": str(e)})
                    return
                except ReviewMergeError as e:
                    self._send_json(502, {"error": str(e)})
                    return
                except subprocess.CalledProcessError as e:
                    self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                    return
            finally:
                instruct_locks.release(repo, issue_number)
                if progress_id:
                    progress_store.clear(progress_id)

            self._refresh_store()
            self._send_json(200, dataclasses.asdict(result))

        def _handle_create_issue(self, repo: str) -> None:
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return

            progress_id: str | None = None
            try:
                payload = self._read_json_body()
                progress_id = payload.get("progressId")
                on_stage = (
                    (lambda stage: progress_store.set(progress_id, stage))
                    if progress_id
                    else (lambda _stage: None)
                )
                result = handle_create_issue(
                    repo,
                    payload["title"],
                    payload["prompt"],
                    payload["dispatch"],
                    create_issue=create_issue,
                    get_labels=get_labels,
                    add_label=add_label,
                    remove_label=remove_label,
                    dispatch_queue=dispatch_queue,
                    on_stage=on_stage,
                )
            except (KeyError, ValueError) as e:
                self._send_json(400, {"error": str(e)})
                return
            except subprocess.CalledProcessError as e:
                self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                return
            finally:
                if progress_id:
                    progress_store.clear(progress_id)

            self._refresh_store()
            self._send_json(201, dataclasses.asdict(result))

    return Handler


def make_server(
    store: StateStore,
    *,
    projects: list[Project],
    dispatch_queue: DispatchQueue,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    get_labels: GetLabelsFn = gh_get_labels,
    add_label: AddLabelFn = gh_add_label,
    remove_label: RemoveLabelFn = gh_remove_label,
    post_comment: PostCommentFn = gh_post_comment,
    create_issue: CreateIssueFn = gh_create_issue,
    daily_model_usage: DailyModelUsageFn = store_daily_model_usage,
    current_limit_status: CurrentLimitStatusFn = store_current_limit_status,
    resolve_pr_number: ResolvePrNumberFn = gh_resolve_pr_number,
    merge_pr: MergePrFn = gh_merge_pr,
    close_issue: CloseIssueFn = gh_close_issue,
    get_pr_branch: GetPrBranchFn = gh_get_pr_branch,
    delete_branch: DeleteBranchFn = gh_delete_branch,
    list_issues: ListIssuesFn = gh_list_issues,
    sync_worktree: SyncWorktreeFn = gh_sync_worktree,
) -> ThreadingHTTPServer:
    known_repos = {project.repo for project in projects}
    handler = _make_handler(
        store,
        projects=projects,
        known_repos=known_repos,
        dispatch_queue=dispatch_queue,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
        post_comment=post_comment,
        create_issue=create_issue,
        daily_model_usage=daily_model_usage,
        current_limit_status=current_limit_status,
        resolve_pr_number=resolve_pr_number,
        merge_pr=merge_pr,
        close_issue=close_issue,
        get_pr_branch=get_pr_branch,
        delete_branch=delete_branch,
        list_issues=list_issues,
        sync_worktree=sync_worktree,
    )
    return ThreadingHTTPServer((host, port), handler)
