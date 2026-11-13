"""「やりたいこと」からAIがissueの計画（タイトル・本文）を作成する（issue #287）。

ダッシュボードの新規タスク作成で「AIに計画してもらう」モードを選んだとき、
`claude -p`をワンショット実行して計画を生成する。**issueはここでは作成しない**
（ユーザーが確認・修正・承認した後に、既存の`POST /api/projects/{repo}/issues`で登録する）。

- 実行はプロジェクトごとのFIFOキュー（`DispatchQueue`）に積み、自走タスクと順番に処理する
  （同一プロジェクトへの同時実行は行わない既存方針）。キューへの投入・worktreeの取得は
  `PlanRunner`に閉じ込め、将来worktreeを動的に作成して並行化する際に差し替えやすくする。
- 既存のworktreeを`origin/develop`の最新（detached HEAD）へ合わせてから実行する。
  未コミットの変更があるworktreeは触らず、現状のまま計画を立てる。
- 計画生成中にファイルを変更させないため、`--permission-mode plan`を指定し、
  書き込み系ツールを`--disallowedTools`で禁止する（`--dangerously-skip-permissions`は使わない）。

仕様: docs/basic-design.md 2-3（計画生成API）・3-6（プロンプト設定）
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

from orchestrator.config import EXECUTION_MODE_LITELLM_PROXY, Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.execution_mode import ExecutionSettings, parse_override_directive
from orchestrator.litellm_proxy import build_env_overrides
from orchestrator.prompts import (
    USER_NAME_SPEC,
    PromptSpec,
    RequiredToken,
    load_overrides_safe,
    render_prompt,
    resolve_prompt_text,
)

logger = logging.getLogger(__name__)

# 計画生成の最大待機時間（実行開始後）。超えたらプロセスを止めてタイムアウトとして返す。
PLAN_TIMEOUT_SECONDS = 600
# 計画生成ジョブがキューに積まれるときのissue番号は負数（実issueと衝突しない）。
PLAN_JOB_NUMBER_START = -1

# 進捗ポーリング（/api/progress/{progress_id}）で返す段階名。キュー順位は`queued:<順位>`。
STAGE_PLAN_QUEUED_PREFIX = "plan_queued:"
STAGE_PLAN_RUNNING = "plan_running"

# 出力形式の必須トークン。編集で失われるとタイトル・本文を機械的に取り出せなくなる。
PLAN_TITLE_KEY = '"title"'
PLAN_BODY_KEY = '"body"'

PLAN_ISSUE_INSTRUCTION_DEFAULT = """\
あなたは{repo}リポジトリのissue計画を作成するアシスタントです。{user_name}の「やりたいこと」を読み、\
このリポジトリのコード・ドキュメントを読み取って調査したうえで、GitHub issueとして登録する\
タイトルと本文（背景・目的・実装方針・受け入れ条件）を日本語で作成してください。

制約:
- ファイルの変更・コミット・ラベル操作・コメント投稿・issue作成は一切行わないこと（読み取りのみ）。
- 既存の計画と修正指示が渡された場合は、指示を反映した修正版の計画を出力すること。

出力形式: 最終応答は次のJSONオブジェクトのみを、```jsonのコードブロックで1つだけ出力すること。\
それ以外の文章は出力しないこと。
```json
{"title": "issueタイトル", "body": "issue本文（Markdown）"}
```
"""

PLAN_ISSUE_SPEC = PromptSpec(
    key="plan_issue_instruction",
    title="issue計画作成の指示",
    description=(
        "新規タスク作成で「AIに計画してもらう」を選んだとき、やりたいことからissueの"
        "タイトル・本文を作成させる指示（修正指示時も同じ指示を使う）"
    ),
    default=PLAN_ISSUE_INSTRUCTION_DEFAULT,
    required_tokens=(
        RequiredToken(
            PLAN_TITLE_KEY,
            "出力JSONのタイトルのキー。無いと計画からタイトルを取り出せず計画生成が失敗します",
        ),
        RequiredToken(
            PLAN_BODY_KEY,
            "出力JSONの本文のキー。無いと計画から本文を取り出せず計画生成が失敗します",
        ),
    ),
    # issue番号は未作成のため展開しない。
    placeholders=("repo", "user_name"),
)


class PlanError(Exception):
    """計画生成の失敗（ユーザー向けメッセージを持つ）。`status`はHTTPステータス。"""

    def __init__(self, message: str, status: int = 502, code: str = "failed") -> None:
        super().__init__(message)
        self.status = status
        # ダッシュボードのエラー表示の種別: parse / timeout / limit / failed
        self.code = code


@dataclass(frozen=True)
class IssuePlan:
    title: str
    body: str


def build_plan_message(
    request: str, previous_plan: IssuePlan | None = None, instruction: str | None = None
) -> str:
    """標準入力へ渡すユーザーメッセージ。"""
    parts = [f"## やりたいこと\n{request.strip()}"]
    if previous_plan is not None:
        parts.append(
            f"## 現在の計画\nタイトル: {previous_plan.title}\n\n本文:\n{previous_plan.body}"
        )
        if instruction and instruction.strip():
            parts.append(f"## 修正指示\n{instruction.strip()}")
    return "\n\n".join(parts)


def build_plan_system_prompt(repo: str, *, prompts_path=None) -> str:
    overrides = load_overrides_safe(prompts_path)
    user_name = resolve_prompt_text(USER_NAME_SPEC, overrides)
    return render_prompt(
        resolve_prompt_text(PLAN_ISSUE_SPEC, overrides),
        repo=repo,
        issue_number=0,
        user_name=user_name,
    )


_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_plan_output(text: str) -> IssuePlan:
    """最終応答からタイトル・本文を取り出す。取り出せなければPlanError。"""
    candidates: list[str] = [m.group(1) for m in _FENCE_PATTERN.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        title, body = data.get("title"), data.get("body")
        if isinstance(title, str) and isinstance(body, str) and title.strip() and body.strip():
            return IssuePlan(title=title.strip(), body=body.strip())
    raise PlanError(
        "AIの出力から計画（タイトル・本文）を読み取れませんでした。再試行してください",
        code="parse",
    )


def prepare_worktree(worktree_path: str, *, run: Callable[..., object] = subprocess.run) -> None:
    """worktreeを`origin/develop`の最新（detached HEAD）に合わせる。

    未コミットの変更がある・fetch/checkoutに失敗した場合は何も変えずログ警告のみ。
    """
    try:
        status = subprocess.run(  # noqa: S603
            ["git", "-C", worktree_path, "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if status.stdout.strip():
            logger.warning(
                "%s に未コミットの変更があるため、develop最新への切替をスキップします",
                worktree_path,
            )
            return
        run(
            ["git", "-C", worktree_path, "fetch", "origin", "develop"],
            capture_output=True,
            text=True,
            check=True,
        )
        run(
            ["git", "-C", worktree_path, "checkout", "--detach", "origin/develop"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        logger.warning(
            "%s をdevelop最新へ合わせられませんでした（現状のまま続行）: %s", worktree_path, e
        )


def build_plan_command(repo: str, *, model: str | None) -> list[str]:
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "plan",
        "--disallowedTools",
        "Edit",
        "Write",
        "NotebookEdit",
        "Bash",
        "--append-system-prompt",
        build_plan_system_prompt(repo),
    ]
    if model is not None:
        command += ["--model", model]
    return command


def _extract_result_text(stdout: str) -> str:
    """`--output-format json`の標準出力から最終応答テキストを取り出す（失敗時は生出力）。"""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout
    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        return payload["result"]
    return stdout


def generate_plan(
    project: Project,
    request: str,
    previous_plan: IssuePlan | None = None,
    instruction: str | None = None,
    *,
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    prepare_worktree_fn: Callable[[str], None] = prepare_worktree,
    timeout_seconds: float = PLAN_TIMEOUT_SECONDS,
    litellm_env_fn: Callable[[Project, ExecutionSettings | None], tuple[str | None, dict[str, str]]]
    | None = None,
    model_override: ExecutionSettings | None = None,
) -> IssuePlan:
    """worktree内で`claude -p`を実行して計画を生成する（呼び出しはキューのワーカー内）。"""
    if not os.path.isdir(project.worktree_path):
        raise PlanError(f"worktreeが見つかりません: {project.worktree_path}")
    prepare_worktree_fn(project.worktree_path)

    model: str | None = None
    env_overrides: dict[str, str] = {}
    if litellm_env_fn is not None:
        model, env_overrides = litellm_env_fn(project, model_override)
    base_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")
    }
    try:
        result = run_command(
            build_plan_command(project.repo, model=model),
            cwd=project.worktree_path,
            input=build_plan_message(request, previous_plan, instruction),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**base_env, **env_overrides},
        )
    except subprocess.TimeoutExpired as e:
        raise PlanError(
            f"計画の生成が{int(timeout_seconds)}秒でタイムアウトしました。再試行してください",
            504,
            "timeout",
        ) from e
    output = result.stdout or ""
    if result.returncode != 0:
        detail = _extract_result_text(output) or (result.stderr or "")
        if re.search(r"limit|usage|rate", detail, re.IGNORECASE):
            raise PlanError(
                "Claudeの利用リミットに達した可能性があります。リセット後に再試行してください",
                429,
                "limit",
            )
        raise PlanError(f"計画の生成に失敗しました（終了コード {result.returncode}）")
    return parse_plan_output(_extract_result_text(output))


class PlanRunner:
    """計画生成ジョブを既存のプロジェクト別FIFOキューに積み、完了まで待つ。

    ジョブは負のissue番号でキューに積み、キューのワーカー（`dispatch_fn`）が
    `run_job`で実行する。呼び出し元（HTTPハンドラ）は`submit`で結果を待つ。
    キューへの投入と実行の入れ替えポイントはこのクラスに集約している。
    """

    def __init__(self, dispatch_queue: DispatchQueue) -> None:
        self._queue = dispatch_queue
        self._lock = threading.Lock()
        self._next = PLAN_JOB_NUMBER_START
        self._jobs: dict[int, _Job] = {}

    def submit(
        self,
        project: Project,
        run: Callable[[], IssuePlan],
        *,
        on_stage: Callable[[str], None],
    ) -> IssuePlan:
        with self._lock:
            job_number = self._next
            self._next -= 1
            job = _Job(run=run, on_stage=on_stage)
            self._jobs[job_number] = job
        self._queue.enqueue(project.repo, job_number, "")
        # キュー順位を進捗として通知しつつ完了を待つ。
        while not job.done.wait(timeout=1.0):
            if not job.started:
                snap = self._queue.snapshot(project.repo, include_plans=True)
                if job_number in snap.waiting:
                    on_stage(f"{STAGE_PLAN_QUEUED_PREFIX}{snap.waiting.index(job_number) + 1}")
        with self._lock:
            self._jobs.pop(job_number, None)
        if job.error is not None:
            raise job.error
        assert job.result is not None
        return job.result

    def run_job(self, job_number: int) -> None:
        with self._lock:
            job = self._jobs.get(job_number)
        if job is None:
            return
        job.started = True
        job.on_stage(STAGE_PLAN_RUNNING)
        try:
            job.result = job.run()
        except PlanError as e:
            job.error = e
        except Exception as e:  # noqa: BLE001
            logger.exception("計画生成で予期しないエラー")
            job.error = PlanError(f"計画の生成中にエラーが発生しました: {e}")
        finally:
            job.done.set()


class _Job:
    def __init__(self, run: Callable[[], IssuePlan], on_stage: Callable[[str], None]) -> None:
        self.run = run
        self.on_stage = on_stage
        self.done = threading.Event()
        self.started = False
        self.result: IssuePlan | None = None
        self.error: PlanError | None = None


def parse_model_choice(value: str | None) -> ExecutionSettings | None:
    """ダッシュボードのモデル選択値（`claude_code` / `litellm:<alias>`）を解釈する。"""
    if not value or value == "default":
        return None
    return parse_override_directive(f"/model {value}")


def execution_env(
    project: Project,
    override: ExecutionSettings | None = None,
    *,
    health_check: Callable[[str], bool],
    base_url: str,
    api_key: str,
) -> tuple[str | None, dict[str, str]]:
    """(B) LiteLLM Proxy選択時のモデル名と環境変数を返す。疎通不能なら(A)へフォールバック。"""
    if override is not None:
        mode, model = override.execution_mode, override.litellm_model
    else:
        mode, model = project.snapshot_execution_settings()
    if mode != EXECUTION_MODE_LITELLM_PROXY or not health_check(base_url):
        return None, {}
    return model, build_env_overrides(
        ExecutionSettings(execution_mode=mode, litellm_model=model),
        base_url=base_url,
        api_key=api_key,
    )
