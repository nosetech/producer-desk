"""orchestrator/plan_jobs.py のテスト（issue #299）。"""

from __future__ import annotations

from orchestrator.plan_jobs import (
    CODE_INTERRUPTED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    PlanJobStore,
)


def test_job_lifecycle_persists_across_reload(tmp_path) -> None:
    path = tmp_path / "jobs.json"
    store = PlanJobStore(path)
    job = store.create("o/r", "やりたい", "claude_code", 12)
    assert job.status == STATUS_QUEUED and job.inbox_issue_number == 12
    store.mark_running(job.id)
    store.mark_succeeded(job.id, "題", "本文")

    reloaded = PlanJobStore(path).get(job.id)

    assert reloaded.status == STATUS_SUCCEEDED
    assert reloaded.result == {"title": "題", "body": "本文"}
    assert reloaded.version == 1


def test_running_jobs_become_failed_interrupted_on_restart(tmp_path) -> None:
    path = tmp_path / "jobs.json"
    store = PlanJobStore(path)
    queued = store.create("o/r", "a", None, None)
    running = store.create("o/r", "b", None, None)
    store.mark_running(running.id)
    assert store.get(running.id).status == STATUS_RUNNING

    reloaded = PlanJobStore(path)

    for job_id in (queued.id, running.id):
        job = reloaded.get(job_id)
        assert job.status == STATUS_FAILED
        assert job.error["code"] == CODE_INTERRUPTED


def test_revise_keeps_previous_result_and_records_history(tmp_path) -> None:
    store = PlanJobStore(tmp_path / "jobs.json")
    job = store.create("o/r", "a", None, None)
    store.mark_succeeded(job.id, "題", "本文")

    revised = store.mark_revising(job.id, "短く", None)

    assert revised.status == STATUS_QUEUED
    assert revised.result == {"title": "題", "body": "本文"}
    assert revised.pending_instruction == "短く"
    assert [h["instruction"] for h in revised.history] == ["短く"]
    store.mark_succeeded(job.id, "題2", "本文2")
    assert store.get(job.id).version == 2 and store.get(job.id).pending_instruction is None


def test_save_edit_only_for_succeeded(tmp_path) -> None:
    store = PlanJobStore(tmp_path / "jobs.json")
    job = store.create("o/r", "a", None, None)
    assert store.save_edit(job.id, "t", "b") is None
    store.mark_succeeded(job.id, "題", "本文")
    assert store.save_edit(job.id, "新題", "新本文").result == {"title": "新題", "body": "新本文"}


def test_save_edit_after_failed_revise_returns_to_review(tmp_path) -> None:
    store = PlanJobStore(tmp_path / "jobs.json")
    job = store.create("o/r", "a", None, None)
    store.mark_succeeded(job.id, "題", "本文")
    store.mark_revising(job.id, "壊す", None)
    store.mark_failed(job.id, "parse", "m")

    back = store.save_edit(job.id, "題", "本文")

    assert back.status == STATUS_SUCCEEDED and back.error is None


def test_prune_inbox_removes_only_finished_jobs_of_closed_inbox(tmp_path) -> None:
    store = PlanJobStore(tmp_path / "jobs.json")
    closed_done = store.create("o/r", "a", None, 1)
    closed_running = store.create("o/r", "b", None, 2)
    store.mark_running(closed_running.id)
    still_open = store.create("o/r", "c", None, 3)
    store.mark_succeeded(still_open.id, "t", "b")
    new_task = store.create("o/r", "d", None, None)
    store.mark_failed(closed_done.id, "failed", "x")
    other_repo = store.create("o/other", "e", None, 1)
    store.mark_failed(other_repo.id, "failed", "x")

    removed = store.prune_inbox("o/r", {3})

    assert removed == [closed_done.id]
    assert store.get(closed_running.id) is not None  # 実行中は完了まで残す
    assert store.get(still_open.id) is not None
    assert store.get(new_task.id) is not None  # 新規タスク由来は承認・破棄まで保持
    assert store.get(other_repo.id) is not None


def test_delete(tmp_path) -> None:
    store = PlanJobStore(tmp_path / "jobs.json")
    job = store.create("o/r", "a", None, None)
    assert store.delete(job.id) is True and store.delete(job.id) is False
    assert store.list("o/r") == []
