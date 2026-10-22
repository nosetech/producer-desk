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
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from orchestrator.agent_runner import AGENT_RUNNER_PROMPT_SPECS
from orchestrator.aggregation import (
    STATUS_COUNT_KEYS,
    AggregatedState,
    IsDispatchActiveFn,
    IssueSummary,
    aggregate,
    build_project_issues,
)
from orchestrator.attachments import AttachmentError, AttachmentResponse, fetch_attachment
from orchestrator.config import DEFAULT_DASHBOARD_SETTINGS, Project
from orchestrator.config import update_project_execution_settings as cfg_update_execution_settings
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.dispatch_status import (
    IssueNotFoundError,
    IssueNotManagedError,
    NoPendingInstructionError,
    RedispatchConflictError,
    diagnose,
    find_issue,
    handle_redispatch,
)
from orchestrator.github_client import (
    CloseIssueFn,
    CreateIssueFn,
    DeleteBranchFn,
    GetIssueDetailFn,
    GetPrBranchFn,
    ListLinkedPrsFn,
    MergePrFn,
    PostCommentFn,
)
from orchestrator.github_client import close_issue as gh_close_issue
from orchestrator.github_client import create_issue as gh_create_issue
from orchestrator.github_client import delete_branch as gh_delete_branch
from orchestrator.github_client import get_issue_detail as gh_get_issue_detail
from orchestrator.github_client import get_pr_branch as gh_get_pr_branch
from orchestrator.github_client import list_issues as gh_list_issues
from orchestrator.github_client import list_linked_prs as gh_list_linked_prs
from orchestrator.github_client import merge_pr as gh_merge_pr
from orchestrator.github_client import post_comment as gh_post_comment
from orchestrator.instruct import (
    APPROVE_DEFAULT_MESSAGE_SPEC,
    PrSelectionRequiredError,
    ReviewMergeError,
    handle_create_issue,
    handle_instruct,
)
from orchestrator.labels import (
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    gh_add_label,
    gh_get_labels,
    gh_remove_label,
)
from orchestrator.polling import ListIssuesFn, fetch_project_issues, now_iso, poll_once
from orchestrator.prompts import (
    USER_NAME_SPEC,
    PromptSpec,
    PromptStorageError,
    PromptValidationError,
    describe_prompt,
    describe_prompts,
    load_overrides_safe,
    reset_prompt_override,
    save_prompt_override,
)
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
# 指示の処理状態チェック・再実行（issue #215）。
DISPATCH_STATUS_PATH = re.compile(
    r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues/(?P<issue_number>\d+)/dispatch-status$"
)
REDISPATCH_PATH = re.compile(
    r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues/(?P<issue_number>\d+)/redispatch$"
)
# 単一issueの本文・コメント取得（issue #231）。返信UIの引用表示用。
ISSUE_DETAIL_PATH = re.compile(
    r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues/(?P<issue_number>\d+)$"
)
CREATE_ISSUE_PATH = re.compile(r"^/api/projects/(?P<repo>[^/]+/[^/]+)/issues$")
# プロジェクト別issue一覧の取得（issue #116）。作成（POST）と同一パス・別メソッド。
LIST_ISSUES_PATH = CREATE_ISSUE_PATH
# プロジェクト単位のissue・ラベル情報の再取得（issue #197）。
REFRESH_PROJECT_PATH = re.compile(r"^/api/projects/(?P<repo>[^/]+/[^/]+)/refresh$")
# 全プロジェクトの再取得（issue #197）。
REFRESH_ALL_PATH = "/api/refresh"
# 読み取り専用モード（issue #241）で書き込み系リクエストを拒否する際のメッセージ。
READ_ONLY_ERROR = "読み取り専用モードのため、書き込み系の操作は実行できません"
PROGRESS_PATH = re.compile(r"^/api/progress/(?P<progress_id>[^/]+)$")
PROJECT_SETTINGS_PATH = re.compile(r"^/api/projects/(?P<repo>[^/]+/[^/]+)/settings$")
# Agent Runnerプロンプト設定（issue #149）。
PROMPTS_PATH = "/api/prompts"
# issueコメント添付ファイルのプロキシ取得（issue #218）。クエリ`url`に添付ファイルのURLを渡す。
ATTACHMENT_PATH = "/api/attachment"
PROMPT_ITEM_PATH = re.compile(r"^/api/prompts/(?P<key>[a-z_]+)$")

# ダッシュボードから閲覧・編集できるプロンプト一覧（表示順）。
PROMPT_SPECS: tuple[PromptSpec, ...] = (
    *AGENT_RUNNER_PROMPT_SPECS,
    APPROVE_DEFAULT_MESSAGE_SPEC,
    USER_NAME_SPEC,
)
PROMPT_SPECS_BY_KEY = {spec.key: spec for spec in PROMPT_SPECS}
# プロンプト本文のPUTリクエスト上限（指示文は数KB程度。LAN内のみだが過大な入力を拒否する）。
MAX_PROMPT_BODY_BYTES = 256 * 1024

DailyModelUsageFn = Callable[..., list[DailyModelUsage]]
CurrentLimitStatusFn = Callable[..., LimitStatus | None]
UpdateExecutionSettingsFn = Callable[..., Project]
FetchAttachmentFn = Callable[..., AttachmentResponse]

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

    def replace_repo(
        self,
        repo: str,
        issues: list[IssueSummary],
        *,
        fetched_at: str,
        is_dispatch_active: IsDispatchActiveFn | None = None,
    ) -> AggregatedState:
        """指定リポジトリ分のissueのみ差し替えて再集約し、保持する（issue #197）。

        他リポジトリのissue・取得時刻と`last_polled_at`は前回の値のまま維持する。
        """
        with self._lock:
            current = self._state
            issues_by_repo = dict(current.issues_by_repo) if current else {}
            fetched_at_by_repo = (
                {p.repo: p.fetched_at for p in current.project_status if p.fetched_at}
                if current
                else {}
            )
            issues_by_repo[repo] = issues
            fetched_at_by_repo[repo] = fetched_at
            self._state = aggregate(
                issues_by_repo,
                is_dispatch_active=is_dispatch_active,
                fetched_at_by_repo=fetched_at_by_repo,
                last_polled_at=current.last_polled_at if current else None,
            )
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
    list_linked_prs: ListLinkedPrsFn,
    merge_pr: MergePrFn,
    close_issue: CloseIssueFn,
    get_pr_branch: GetPrBranchFn,
    delete_branch: DeleteBranchFn,
    list_issues: ListIssuesFn,
    sync_worktree: SyncWorktreeFn,
    get_issue_detail: GetIssueDetailFn,
    dashboard_settings: dict[str, float],
    update_execution_settings: UpdateExecutionSettingsFn = cfg_update_execution_settings,
    github_token: str | None = None,
    fetch_attachment_fn: FetchAttachmentFn = fetch_attachment,
    read_only: bool = False,
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

        def _refresh_store(self) -> bool:
            """instruct/create_issue成功直後にStateStoreを同期更新する（issue #70）。

            バックグラウンドポーリング（5分間隔）を待たずダッシュボードの再取得
            （GET /api/state）に最新状態を反映させ、カードが消えないまま二重操作
            できてしまう不具合を防ぐ。再取得自体の失敗は指示操作の成功を損なわないよう
            ログ警告に留め、次回のバックグラウンドポーリングでの復旧に委ねる。
            成功したかどうかを返す（全プロジェクト再取得エンドポイントが利用、issue #197）。
            """
            try:
                state = poll_once(
                    projects,
                    list_issues=list_issues,
                    list_linked_prs=list_linked_prs,
                    is_dispatch_active=dispatch_queue.is_active,
                )
            except subprocess.CalledProcessError as e:
                logger.warning("instruct成功後のstate再取得に失敗しました: %s", e)
                return False
            store.set(state)
            return True

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandlerのインターフェースに合わせる)
            if self.path == "/api/state":
                self._handle_state()
                return
            if self.path == "/api/usage":
                self._handle_usage()
                return
            if self.path == "/api/settings":
                self._send_json(200, dict(dashboard_settings))
                return
            if self.path == PROMPTS_PATH:
                self._send_json(200, {"prompts": describe_prompts(PROMPT_SPECS)})
                return
            if urllib.parse.urlsplit(self.path).path == ATTACHMENT_PATH:
                self._handle_attachment()
                return

            progress_match = PROGRESS_PATH.match(self.path)
            if progress_match:
                self._handle_progress(progress_match.group("progress_id"))
                return

            dispatch_status_match = DISPATCH_STATUS_PATH.match(self.path)
            if dispatch_status_match:
                self._handle_dispatch_status(
                    dispatch_status_match.group("repo"),
                    int(dispatch_status_match.group("issue_number")),
                )
                return

            issue_detail_match = ISSUE_DETAIL_PATH.match(self.path)
            if issue_detail_match:
                self._handle_issue_detail(
                    issue_detail_match.group("repo"),
                    int(issue_detail_match.group("issue_number")),
                )
                return

            list_issues_match = LIST_ISSUES_PATH.match(self.path)
            if list_issues_match:
                self._handle_list_issues(list_issues_match.group("repo"))
                return

            self.send_response(404)
            self.end_headers()

        def _handle_issue_detail(self, repo: str, issue_number: int) -> None:
            """単一issueの本文とコメントを返す（issue #231）。"""
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return
            try:
                detail = get_issue_detail(repo, issue_number)
            except subprocess.CalledProcessError as e:
                logger.warning("issueの詳細取得に失敗しました (%s#%s): %s", repo, issue_number, e)
                self._send_json(502, {"error": f"{repo}#{issue_number} を取得できませんでした"})
                return
            self._send_json(200, detail)

        def _handle_list_issues(self, repo: str) -> None:
            """プロジェクト別issue一覧（issue #116）。

            詳細ページを開く操作は低頻度のため、StateStoreにキャッシュせずリクエスト都度
            `list_issues`（`gh issue list`）で取得する。
            """
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return
            try:
                issues = list_issues(repo)
            except subprocess.CalledProcessError as e:
                logger.warning("issue一覧の取得に失敗しました (%s): %s", repo, e)
                self._send_json(502, {"error": f"{repo} のissue一覧を取得できませんでした"})
                return
            self._send_json(
                200,
                {
                    "repo": repo,
                    "issues": [
                        dataclasses.asdict(i)
                        for i in build_project_issues(issues, dispatch_queue.is_active)
                    ],
                },
            )

        def _state_payload(self, state: AggregatedState | None) -> dict:
            if state is None:
                return {
                    "decisions": [],
                    "reviews": [],
                    "project_status": [],
                    "status_counts": dict.fromkeys(STATUS_COUNT_KEYS, 0),
                    "last_polled_at": None,
                }
            payload = dataclasses.asdict(state)
            payload.pop("issues_by_repo", None)  # 内部用データ。APIには含めない
            return payload

        def _handle_refresh_project(self, repo: str) -> None:
            """1プロジェクト分のissue・ラベル情報をGitHubから再取得する（issue #197）。

            全プロジェクトを走査する`poll_once`ではなく、当該リポジトリのみ取得して
            StateStoreを差し替え再集約する。取得失敗時はStateStoreを変更しない。
            """
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return
            try:
                issues = fetch_project_issues(
                    projects_by_repo[repo],
                    list_issues=list_issues,
                    list_linked_prs=list_linked_prs,
                )
            except subprocess.CalledProcessError as e:
                logger.warning("プロジェクト再取得に失敗しました (%s): %s", repo, e)
                self._send_json(502, {"error": f"{repo} の情報を再取得できませんでした"})
                return
            fetched_at = now_iso()
            state = store.replace_repo(
                repo, issues, fetched_at=fetched_at, is_dispatch_active=dispatch_queue.is_active
            )
            self._send_json(
                200,
                {
                    "repo": repo,
                    "fetched_at": fetched_at,
                    "issues": [
                        dataclasses.asdict(i)
                        for i in build_project_issues(issues, dispatch_queue.is_active)
                    ],
                    "state": self._state_payload(state),
                },
            )

        def _handle_refresh_all(self) -> None:
            """全プロジェクトの情報を再取得してStateStoreを更新する（issue #197）。"""
            if not self._refresh_store():
                self._send_json(502, {"error": "プロジェクト情報を再取得できませんでした"})
                return
            self._send_json(200, self._state_payload(store.get()))

        def _handle_progress(self, progress_id: str) -> None:
            self._send_json(200, {"stage": progress_store.get(progress_id)})

        def _handle_attachment(self) -> None:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            urls = query.get("url", [])
            if len(urls) != 1:
                self._send_json(400, {"error": "urlクエリを1つ指定してください"})
                return
            try:
                attachment = fetch_attachment_fn(
                    urls[0], token=github_token, range_header=self.headers.get("Range")
                )
            except AttachmentError as e:
                logger.warning("添付ファイルを取得できませんでした: %s", e)
                self._send_json(e.status, {"error": str(e)})
                return
            try:
                self.send_response(attachment.status)
                for name, value in attachment.headers.items():
                    self.send_header(name, value)
                # 署名付きURL先の内容をそのまま中継するため、ブラウザ側での再利用は短時間に留める。
                self.send_header("Cache-Control", "private, max-age=300")
                self.end_headers()
                while chunk := attachment.body.read(64 * 1024):
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # 動画のシーク等でブラウザが接続を切った
            finally:
                attachment.body.close()

        def _handle_state(self) -> None:
            self._send_json(200, self._state_payload(store.get()))

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

        def _reject_if_read_only(self) -> bool:
            """読み取り専用モード（issue #241）なら403を返し、Trueを返す。"""
            if read_only:
                self._send_json(403, {"error": READ_ONLY_ERROR})
            return read_only

        def do_POST(self) -> None:  # noqa: N802
            # 再取得（GET相当の参照のみ）は読み取り専用モードでも許可する。
            if self.path == REFRESH_ALL_PATH:
                self._handle_refresh_all()
                return

            refresh_match = REFRESH_PROJECT_PATH.match(self.path)
            if refresh_match:
                self._handle_refresh_project(refresh_match.group("repo"))
                return

            if self._reject_if_read_only():
                return

            instruct_match = INSTRUCT_PATH.match(self.path)
            if instruct_match:
                self._handle_instruct(
                    instruct_match.group("repo"), int(instruct_match.group("issue_number"))
                )
                return

            redispatch_match = REDISPATCH_PATH.match(self.path)
            if redispatch_match:
                self._handle_redispatch(
                    redispatch_match.group("repo"), int(redispatch_match.group("issue_number"))
                )
                return

            create_issue_match = CREATE_ISSUE_PATH.match(self.path)
            if create_issue_match:
                self._handle_create_issue(create_issue_match.group("repo"))
                return

            self._send_json(404, {"error": "not found"})

        def do_PATCH(self) -> None:  # noqa: N802
            if self._reject_if_read_only():
                return

            settings_match = PROJECT_SETTINGS_PATH.match(self.path)
            if settings_match:
                self._handle_update_project_settings(settings_match.group("repo"))
                return

            self._send_json(404, {"error": "not found"})

        def do_PUT(self) -> None:  # noqa: N802
            if self._reject_if_read_only():
                return

            prompt_match = PROMPT_ITEM_PATH.match(self.path)
            if prompt_match:
                self._handle_update_prompt(prompt_match.group("key"))
                return

            self._send_json(404, {"error": "not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            if self._reject_if_read_only():
                return

            prompt_match = PROMPT_ITEM_PATH.match(self.path)
            if prompt_match:
                self._handle_reset_prompt(prompt_match.group("key"))
                return

            self._send_json(404, {"error": "not found"})

        def _find_prompt_spec(self, key: str) -> PromptSpec | None:
            return PROMPT_SPECS_BY_KEY.get(key)

        def _handle_update_prompt(self, key: str) -> None:
            """issue #149: プロンプト本文を検証のうえ`config/prompts.yaml`に保存する。

            次回のAgent Runner起動（`build_claude_command`）から反映される。
            """
            spec = self._find_prompt_spec(key)
            if spec is None:
                self._send_json(404, {"error": f"未知のプロンプトです: {key}"})
                return
            if int(self.headers.get("Content-Length", 0)) > MAX_PROMPT_BODY_BYTES:
                self._send_json(413, {"error": "リクエストが大きすぎます"})
                return
            try:
                body = self._read_json_body()
                if not isinstance(body, dict):
                    raise ValueError("リクエストボディはJSONオブジェクトである必要があります")
                text = body["text"]
                if not isinstance(text, str):
                    raise ValueError("textは文字列である必要があります")
                save_prompt_override(spec, text)
            except PromptValidationError as e:
                self._send_json(400, {"error": str(e), "errors": e.errors})
                return
            except KeyError:
                self._send_json(400, {"error": "textは必須です"})
                return
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            except PromptStorageError as e:
                logger.warning("プロンプトの保存に失敗しました (%s): %s", key, e)
                self._send_json(500, {"error": str(e)})
                return
            self._send_json(200, describe_prompt(spec, load_overrides_safe()))

        def _handle_reset_prompt(self, key: str) -> None:
            """issue #149: プロンプトの上書きを削除しデフォルトに戻す。"""
            spec = self._find_prompt_spec(key)
            if spec is None:
                self._send_json(404, {"error": f"未知のプロンプトです: {key}"})
                return
            try:
                reset_prompt_override(spec)
            except PromptStorageError as e:
                logger.warning("プロンプトのリセットに失敗しました (%s): %s", key, e)
                self._send_json(500, {"error": str(e)})
                return
            self._send_json(200, describe_prompt(spec, load_overrides_safe()))

        def _handle_update_project_settings(self, repo: str) -> None:
            """issue #176: プロジェクトごとの実行手段デフォルト設定を更新する。

            issue #175（ダッシュボードのプロジェクト設定UI）はこのAPIを呼び出す
            想定。`config/projects.yaml`への永続化に加え、再起動を待たず次回
            ディスパッチから反映されるよう、サーバー起動時に読み込み済みの
            `Project`インスタンスをその場で書き換える（`projects`/
            `projects_by_repo`、および`main.py`の`_make_dispatch_fn`が参照する
            インスタンスは同一オブジェクトのため、この変更は両方に反映される）。
            """
            project = projects_by_repo.get(repo)
            if project is None:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return

            try:
                payload = self._read_json_body()
                execution_mode = payload["execution_mode"]
                litellm_model = payload.get("litellm_model")
                updated = update_execution_settings(repo, execution_mode, litellm_model)
            except (KeyError, ValueError) as e:
                self._send_json(400, {"error": str(e)})
                return

            # 2フィールドを別々の代入で書き換えると、ディスパッチ中の別スレッドから
            # 一時的に不整合な組み合わせ（新execution_mode・旧litellm_model等）が
            # 観測されうるため、`Project.execution_lock`で保護された
            # `replace_execution_settings`でまとめて更新する。
            project.replace_execution_settings(updated.execution_mode, updated.litellm_model)
            self._send_json(
                200,
                {
                    "repo": repo,
                    "execution_mode": updated.execution_mode,
                    "litellm_model": updated.litellm_model,
                },
            )

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
                    try:
                        payload = self._read_json_body()
                        progress_id = payload.get("progressId")
                        on_stage = (
                            (lambda stage: progress_store.set(progress_id, stage))
                            if progress_id
                            else (lambda _stage: None)
                        )
                        pr_number = payload.get("prNumber")
                        if pr_number is not None and (
                            not isinstance(pr_number, int) or isinstance(pr_number, bool)
                        ):
                            raise ValueError("prNumberは整数で指定してください")
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
                            list_linked_prs=list_linked_prs,
                            merge_pr=merge_pr,
                            close_issue=close_issue,
                            get_pr_branch=get_pr_branch,
                            delete_branch=delete_branch,
                            worktree_path=projects_by_repo[repo].worktree_path,
                            sync_worktree=sync_worktree,
                            on_stage=on_stage,
                            pr_number=pr_number,
                        )
                    except (KeyError, ValueError) as e:
                        self._send_json(400, {"error": str(e)})
                        return
                    except PrSelectionRequiredError as e:
                        # 対応PRを一意に特定できない場合は自動マージせず、候補を返して
                        # ダッシュボードにPR選択UIを開かせる（issue #206）。
                        self._send_json(
                            409,
                            {
                                "error": str(e),
                                "code": "pr_selection_required",
                                "pr_candidates": [dataclasses.asdict(c) for c in e.candidates],
                            },
                        )
                        return
                    except ReviewMergeError as e:
                        self._send_json(502, {"error": str(e)})
                        return
                    except subprocess.CalledProcessError as e:
                        self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                        return
                finally:
                    instruct_locks.release(repo, issue_number)

                self._refresh_store()
                self._send_json(200, dataclasses.asdict(result))
            finally:
                # progress_storeのクリアは、_refresh_store・_send_jsonが完了し
                # クライアントへの応答が完全に済んだ後に行う（issue報告: 「worktreeを
                # 同期」完了後に「PRをマージ」が再度アクティブ表示される不具合）。
                # ここより前でクリアすると、_refresh_store（gh APIでのissue一覧再取得
                # を伴い数百ms〜数秒かかりうる）の実行中にダッシュボードの
                # /api/progress ポーリングが空振り（stage: null）を観測してしまい、
                # まだ何も完了していない状態と誤解して先頭の段階を再度アクティブ表示
                # してしまっていた。
                if progress_id:
                    progress_store.clear(progress_id)

        def _fetch_issue(self, repo: str, issue_number: int) -> IssueSummary | None:
            """対象issueを取得する。失敗時は応答を送信済みでNoneを返す。"""
            try:
                return find_issue(list_issues(repo), issue_number)
            except IssueNotFoundError as e:
                self._send_json(404, {"error": str(e)})
            except subprocess.CalledProcessError as e:
                logger.warning("issueの取得に失敗しました (%s#%s): %s", repo, issue_number, e)
                self._send_json(502, {"error": f"{repo}#{issue_number} を取得できませんでした"})
            return None

        def _handle_dispatch_status(self, repo: str, issue_number: int) -> None:
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
                return
            issue = self._fetch_issue(repo, issue_number)
            if issue is None:
                return
            status = diagnose(issue, dispatch_queue)
            self._send_json(200, dataclasses.asdict(status))

        def _handle_redispatch(self, repo: str, issue_number: int) -> None:
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
                    try:
                        payload = self._read_json_body()
                        if not isinstance(payload, dict):
                            payload = {}
                        progress_id = payload.get("progressId")
                        if not isinstance(progress_id, str):
                            progress_id = None
                    except ValueError:
                        payload = {}
                    on_stage = (
                        (lambda stage: progress_store.set(progress_id, stage))
                        if progress_id
                        else (lambda _stage: None)
                    )
                    issue = self._fetch_issue(repo, issue_number)
                    if issue is None:
                        return
                    status = handle_redispatch(
                        issue,
                        get_labels=get_labels,
                        add_label=add_label,
                        remove_label=remove_label,
                        post_comment=post_comment,
                        dispatch_queue=dispatch_queue,
                        on_stage=on_stage,
                    )
                except RedispatchConflictError as e:
                    self._send_json(409, {"error": str(e)})
                    return
                except NoPendingInstructionError as e:
                    self._send_json(422, {"error": str(e)})
                    return
                except IssueNotManagedError as e:
                    self._send_json(400, {"error": str(e)})
                    return
                except subprocess.CalledProcessError as e:
                    self._send_json(502, {"error": f"ghコマンドが失敗しました: {e}"})
                    return
                finally:
                    instruct_locks.release(repo, issue_number)

                self._refresh_store()
                self._send_json(
                    200,
                    {"dispatched": True, "comment": status.pending_message, "state": status.state},
                )
            finally:
                if progress_id:
                    progress_store.clear(progress_id)

        def _handle_create_issue(self, repo: str) -> None:
            if repo not in known_repos:
                self._send_json(404, {"error": f"未登録のリポジトリです: {repo}"})
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

                self._refresh_store()
                self._send_json(201, dataclasses.asdict(result))
            finally:
                # _handle_instructと同様、progress_storeのクリアは応答が完全に
                # 済んだ後に行う（クリア直後のポーリング空振りによる段階表示の
                # 巻き戻りを防ぐため）。
                if progress_id:
                    progress_store.clear(progress_id)

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
    list_linked_prs: ListLinkedPrsFn = gh_list_linked_prs,
    merge_pr: MergePrFn = gh_merge_pr,
    close_issue: CloseIssueFn = gh_close_issue,
    get_pr_branch: GetPrBranchFn = gh_get_pr_branch,
    delete_branch: DeleteBranchFn = gh_delete_branch,
    list_issues: ListIssuesFn = gh_list_issues,
    sync_worktree: SyncWorktreeFn = gh_sync_worktree,
    get_issue_detail: GetIssueDetailFn = gh_get_issue_detail,
    update_execution_settings: UpdateExecutionSettingsFn = cfg_update_execution_settings,
    dashboard_settings: dict[str, float] | None = None,
    github_token: str | None = None,
    fetch_attachment_fn: FetchAttachmentFn = fetch_attachment,
    read_only: bool = False,
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
        list_linked_prs=list_linked_prs,
        merge_pr=merge_pr,
        close_issue=close_issue,
        get_pr_branch=get_pr_branch,
        delete_branch=delete_branch,
        list_issues=list_issues,
        sync_worktree=sync_worktree,
        get_issue_detail=get_issue_detail,
        update_execution_settings=update_execution_settings,
        github_token=github_token,
        fetch_attachment_fn=fetch_attachment_fn,
        read_only=read_only,
        dashboard_settings=(
            dashboard_settings if dashboard_settings is not None else DEFAULT_DASHBOARD_SETTINGS
        ),
    )
    return ThreadingHTTPServer((host, port), handler)
