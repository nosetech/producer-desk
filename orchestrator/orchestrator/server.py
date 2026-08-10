"""ダッシュボード（Next.js）とオーケストレータ間の内部API。

仕様:
- docs/basic-design.md 2-2（GET /api/state、ダッシュボード表示用の集約データ提供）
- docs/basic-design.md 2-3（指示出しAPI: POST /api/projects/{repo}/issues/{issue_number}/instruct
  と POST /api/projects/{repo}/issues）
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orchestrator.aggregation import AggregatedState
from orchestrator.config import Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import CreateIssueFn, PostCommentFn
from orchestrator.github_client import create_issue as gh_create_issue
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.instruct import handle_create_issue, handle_instruct
from orchestrator.labels import (
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    gh_add_label,
    gh_get_labels,
    gh_remove_label,
)
from orchestrator.usage_store import DailyModelUsage, LimitStatus
from orchestrator.usage_store import current_limit_status as store_current_limit_status
from orchestrator.usage_store import daily_model_usage as store_daily_model_usage

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

INSTRUCT_PATH = re.compile(
    r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues/(?P<issue_number>\d+)/instruct$"
)
CREATE_ISSUE_PATH = re.compile(r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues$")

DailyModelUsageFn = Callable[..., list[DailyModelUsage]]
CurrentLimitStatusFn = Callable[..., LimitStatus | None]


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


def _make_handler(
    store: StateStore,
    *,
    known_repos: set[str],
    dispatch_queue: DispatchQueue,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    post_comment: PostCommentFn,
    create_issue: CreateIssueFn,
    daily_model_usage: DailyModelUsageFn,
    current_limit_status: CurrentLimitStatusFn,
) -> type[BaseHTTPRequestHandler]:
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

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandlerのインターフェースに合わせる)
            if self.path == "/api/state":
                self._handle_state()
                return
            if self.path == "/api/usage":
                self._handle_usage()
                return

            self.send_response(404)
            self.end_headers()

        def _handle_state(self) -> None:
            state = store.get()
            self._send_json(
                200,
                dataclasses.asdict(state)
                if state is not None
                else {"decisions": [], "activity": []},
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

            try:
                payload = self._read_json_body()
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
                )
            except (KeyError, ValueError) as e:
                self._send_json(400, {"error": str(e)})
                return
            except subprocess.CalledProcessError as e:
                self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                return

            self._send_json(200, dataclasses.asdict(result))

        def _handle_create_issue(self, repo: str) -> None:
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return

            try:
                payload = self._read_json_body()
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
                )
            except (KeyError, ValueError) as e:
                self._send_json(400, {"error": str(e)})
                return
            except subprocess.CalledProcessError as e:
                self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                return

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
) -> ThreadingHTTPServer:
    known_repos = {project.repo for project in projects}
    handler = _make_handler(
        store,
        known_repos=known_repos,
        dispatch_queue=dispatch_queue,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
        post_comment=post_comment,
        create_issue=create_issue,
        daily_model_usage=daily_model_usage,
        current_limit_status=current_limit_status,
    )
    return ThreadingHTTPServer((host, port), handler)
