"""orchestrator/issue_plan.py のテスト（issue #287）。"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from orchestrator.config import Project
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.issue_plan import (
    PLAN_ISSUE_SPEC,
    IssuePlan,
    PlanError,
    PlanRunner,
    build_plan_message,
    generate_plan,
    parse_plan_output,
)
from orchestrator.plan_jobs import PlanJobStore
from orchestrator.prompts import validate_prompt_text


def test_default_prompt_is_valid() -> None:
    assert validate_prompt_text(PLAN_ISSUE_SPEC, PLAN_ISSUE_SPEC.default) == []


def test_prompt_rejects_issue_number_placeholder_and_missing_keys() -> None:
    errors = validate_prompt_text(PLAN_ISSUE_SPEC, "{issue_number} だけ")

    assert any("{issue_number}" in e for e in errors)
    assert any('"title"' in e for e in errors)
    assert any('"body"' in e for e in errors)


def test_parse_fenced_json() -> None:
    text = '説明\n```json\n{"title": "T", "body": "B"}\n```\n'

    assert parse_plan_output(text) == IssuePlan("T", "B")


def test_parse_bare_json() -> None:
    assert parse_plan_output('{"title": "T", "body": "B"}') == IssuePlan("T", "B")


@pytest.mark.parametrize("text", ["", "JSONなし", '{"title": "T"}', '{"title": "", "body": "B"}'])
def test_parse_failure(text: str) -> None:
    with pytest.raises(PlanError):
        parse_plan_output(text)


def test_build_message_includes_previous_plan_and_instruction() -> None:
    message = build_plan_message("やりたい", IssuePlan("旧T", "旧B"), "短くして")

    assert "やりたい" in message and "旧T" in message and "短くして" in message
    assert "修正指示" not in build_plan_message("やりたい", IssuePlan("a", "b"), None)


def _project(tmp_path) -> Project:
    return Project(repo="o/r", worktree_path=str(tmp_path))


def _result(stdout: str, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_generate_plan_runs_read_only_command(tmp_path) -> None:
    calls: list[dict] = []

    def run_command(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return _result(json.dumps({"result": '```json\n{"title": "T", "body": "B"}\n```'}))

    plan = generate_plan(
        _project(tmp_path), "やりたい", run_command=run_command, prepare_worktree_fn=lambda _p: None
    )

    assert plan == IssuePlan("T", "B")
    command = calls[0]["command"]
    assert "--dangerously-skip-permissions" not in command
    assert command[command.index("--permission-mode") + 1] == "plan"
    assert calls[0]["cwd"] == str(tmp_path)


def test_generate_plan_timeout(tmp_path) -> None:
    def run_command(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    with pytest.raises(PlanError) as e:
        generate_plan(
            _project(tmp_path), "x", run_command=run_command, prepare_worktree_fn=lambda _p: None
        )

    assert e.value.status == 504


def test_generate_plan_usage_limit(tmp_path) -> None:
    def run_command(command, **kwargs):
        return _result(json.dumps({"result": "Claude usage limit reached"}), returncode=1)

    with pytest.raises(PlanError) as e:
        generate_plan(
            _project(tmp_path), "x", run_command=run_command, prepare_worktree_fn=lambda _p: None
        )

    assert e.value.status == 429


def test_generate_plan_unparsable_output(tmp_path) -> None:
    with pytest.raises(PlanError):
        generate_plan(
            _project(tmp_path),
            "x",
            run_command=lambda c, **k: _result(json.dumps({"result": "計画なし"})),
            prepare_worktree_fn=lambda _p: None,
        )


def test_generate_plan_missing_worktree(tmp_path) -> None:
    project = Project(repo="o/r", worktree_path=str(tmp_path / "none"))

    with pytest.raises(PlanError):
        generate_plan(project, "x")


def test_plan_runner_serializes_with_issue_dispatch(tmp_path) -> None:
    """計画生成は実issueのディスパッチと同じキューで順番に処理され、結果はストアへ書かれる。"""
    order: list[str] = []
    release = threading.Event()
    finished: list[str] = []
    runner_ref: list[PlanRunner] = []

    def dispatch_fn(repo: str, number: int, message: str) -> None:
        if number < 0:
            runner_ref[0].run_job(number)
        else:
            order.append(f"issue{number}")
            release.wait(timeout=5)

    queue = DispatchQueue(dispatch_fn)
    store = PlanJobStore(tmp_path / "jobs.json")
    runner = PlanRunner(queue, store, on_finished=lambda job: finished.append(job.status))
    runner_ref.append(runner)
    queue.enqueue("o/r", 5, "msg")
    job = store.create("o/r", "req", None, None)
    # enqueueは待たずに即時戻る。issueが実行中なので、計画生成はキューで待機する
    runner.enqueue(
        _project(tmp_path), job.id, lambda: (order.append("plan"), IssuePlan("T", "B"))[1]
    )
    snap = queue.snapshot("o/r")
    assert snap.running == 5 and snap.waiting == []  # 計画ジョブは実issueの表示に混ざらない
    assert runner.position("o/r", job.id) == 1
    assert store.get(job.id).status == "queued"
    release.set()
    for _ in range(100):
        if finished:
            break
        time.sleep(0.05)

    assert order == ["issue5", "plan"]
    done = store.get(job.id)
    assert done.status == "succeeded" and done.result == {"title": "T", "body": "B"}
    assert finished == ["succeeded"]
    assert runner.position("o/r", job.id) is None


def test_plan_runner_job_id_for_resolves_queued_job_number(tmp_path) -> None:
    """キュー上のジョブ番号（負数）から計画ジョブIDを引ける（issue #335）。"""
    gate = threading.Event()
    runner_ref: list[PlanRunner] = []

    def dispatch_fn(repo: str, number: int, message: str) -> None:
        if number < 0:
            runner_ref[0].run_job(number)
        else:
            gate.wait(timeout=5)

    queue = DispatchQueue(dispatch_fn)
    store = PlanJobStore(tmp_path / "jobs.json")
    runner = PlanRunner(queue, store)
    runner_ref.append(runner)
    queue.enqueue("o/r", 1, "")
    job = store.create("o/r", "req", None, None)
    runner.enqueue(_project(tmp_path), job.id, lambda: IssuePlan("T", "B"))
    number = queue.snapshot("o/r", include_plans=True).waiting[0]

    assert number < 0
    assert runner.job_id_for(number) == job.id
    assert runner.job_id_for(number - 1) is None
    gate.set()
    for _ in range(100):
        if not runner.is_active(job.id):
            break
        time.sleep(0.05)
    assert runner.job_id_for(number) is None


def test_plan_runner_records_failure_with_code(tmp_path) -> None:
    runner_ref: list[PlanRunner] = []
    queue = DispatchQueue(lambda repo, n, m: runner_ref[0].run_job(n))
    store = PlanJobStore(tmp_path / "jobs.json")
    finished: list[str] = []
    runner = PlanRunner(queue, store, on_finished=lambda job: finished.append(job.status))
    runner_ref.append(runner)
    job = store.create("o/r", "req", None, None)

    def boom() -> IssuePlan:
        raise PlanError("時間切れ", 504, "timeout")

    runner.enqueue(_project(tmp_path), job.id, boom)
    for _ in range(100):
        if finished:
            break
        time.sleep(0.05)

    failed = store.get(job.id)
    assert failed.status == "failed" and failed.error == {"code": "timeout", "message": "時間切れ"}


def test_plan_runner_skips_discarded_job(tmp_path) -> None:
    ran: list[int] = []
    runner_ref: list[PlanRunner] = []
    gate = threading.Event()

    def dispatch_fn(repo: str, number: int, message: str) -> None:
        if number < 0:
            runner_ref[0].run_job(number)
        else:
            gate.wait(timeout=5)

    queue = DispatchQueue(dispatch_fn)
    store = PlanJobStore(tmp_path / "jobs.json")
    runner = PlanRunner(queue, store)
    runner_ref.append(runner)
    queue.enqueue("o/r", 1, "")
    job = store.create("o/r", "req", None, None)
    runner.enqueue(_project(tmp_path), job.id, lambda: (ran.append(1), IssuePlan("T", "B"))[1])
    store.delete(job.id)  # キュー待ち中に破棄
    gate.set()
    for _ in range(40):
        if not runner.is_active(job.id):
            break
        time.sleep(0.05)

    assert ran == [] and store.get(job.id) is None


def test_parse_model_choice() -> None:
    from orchestrator.issue_plan import parse_model_choice

    assert parse_model_choice(None) is None
    assert parse_model_choice("default") is None
    assert parse_model_choice("claude_code").execution_mode == "claude_code"
    chosen = parse_model_choice("litellm:ollama/qwen")
    assert chosen.execution_mode == "litellm_proxy" and chosen.litellm_model == "ollama/qwen"
