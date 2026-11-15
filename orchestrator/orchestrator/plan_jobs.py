"""AI計画ジョブの永続化ストア（issue #299）。

「AIに計画してもらう」を非同期（バックグラウンド実行）にするため、計画ジョブを
ローカルJSONファイル（`config/plan_jobs.json`、.gitignore対象）に保持する。
GitHubが正のデータストアという方針のうえで、issue未作成の一時データだけを持つ。

- 保持期間: 承認（issue登録）または破棄されるまで。時間経過では削除しない。
  inbox由来のジョブは、対象inbox項目がOPENのinboxでなくなった時点で破棄する。
- 再起動時に`queued`/`running`のまま残ったジョブは`failed`（code=`interrupted`）にする。

仕様: docs/basic-design.md 2-3（AIによる計画作成）
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.config import REPO_ROOT

DEFAULT_PLAN_JOBS_PATH = REPO_ROOT / "config" / "plan_jobs.json"
PLAN_JOBS_PATH_ENV = "PLAN_JOBS_PATH"

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

# 再起動で中断されたジョブのエラー種別。
CODE_INTERRUPTED = "interrupted"
INTERRUPTED_MESSAGE = "オーケストレータの再起動により中断されました。再試行してください"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class PlanJob:
    id: str
    repo: str
    request: str
    model: str | None
    inbox_issue_number: int | None
    status: str
    created_at: str
    updated_at: str
    result: dict | None = None  # {"title", "body"}。修正中は直前の結果を残す
    error: dict | None = None  # {"code", "message"}
    # 修正指示の履歴（最初の依頼は`request`）。{"instruction", "at"}
    history: list[dict] = field(default_factory=list)
    # 実行中の修正指示（初回生成のときはNone）。
    pending_instruction: str | None = None
    # 版: 生成に成功するたびに+1（初回成功で1）。
    version: int = 0

    def to_json(self) -> dict:
        """APIレスポンス用（camelCase）。"""
        return {
            "id": self.id,
            "repo": self.repo,
            "request": self.request,
            "model": self.model,
            "inboxIssueNumber": self.inbox_issue_number,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "history": self.history,
            "pendingInstruction": self.pending_instruction,
            "version": self.version,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class PlanJobStore:
    """スレッドセーフなJSONファイル永続ストア。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(os.environ.get(PLAN_JOBS_PATH_ENV, str(DEFAULT_PLAN_JOBS_PATH)))
        self._lock = threading.RLock()
        self._jobs: dict[str, PlanJob] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        changed = False
        for item in raw if isinstance(raw, list) else []:
            try:
                job = PlanJob(**item)
            except TypeError:
                continue
            if job.status in (STATUS_QUEUED, STATUS_RUNNING):
                job.status = STATUS_FAILED
                job.error = {"code": CODE_INTERRUPTED, "message": INTERRUPTED_MESSAGE}
                job.pending_instruction = None
                job.updated_at = _now()
                changed = True
            self._jobs[job.id] = job
        if changed:
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(j) for j in self._jobs.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def create(
        self,
        repo: str,
        request: str,
        model: str | None,
        inbox_issue_number: int | None,
    ) -> PlanJob:
        with self._lock:
            now = _now()
            job = PlanJob(
                id=uuid.uuid4().hex,
                repo=repo,
                request=request,
                model=model,
                inbox_issue_number=inbox_issue_number,
                status=STATUS_QUEUED,
                created_at=now,
                updated_at=now,
            )
            self._jobs[job.id] = job
            self._save()
            return job

    def get(self, job_id: str) -> PlanJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, repo: str) -> list[PlanJob]:
        with self._lock:
            return sorted(
                (j for j in self._jobs.values() if j.repo == repo), key=lambda j: j.created_at
            )

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = STATUS_RUNNING
            job.updated_at = _now()
            self._save()

    def mark_revising(self, job_id: str, instruction: str, model: str | None) -> PlanJob | None:
        """修正指示の投入。直前の結果は残したまま`queued`に戻す。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = STATUS_QUEUED
            job.error = None
            job.pending_instruction = instruction
            job.history.append({"instruction": instruction, "at": _now()})
            if model is not None:
                job.model = model
            job.updated_at = _now()
            self._save()
            return job

    def mark_retrying(self, job_id: str, instruction: str | None = None) -> PlanJob | None:
        """失敗ジョブの再試行（直前の結果・修正指示を引き継いで再投入）。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = STATUS_QUEUED
            job.error = None
            job.pending_instruction = instruction
            job.updated_at = _now()
            self._save()
            return job

    def save_edit(self, job_id: str, title: str, body: str) -> PlanJob | None:
        """確認画面での直接編集の保存（AIの再生成はしない）。

        修正に失敗した（直前の計画`result`が残っている）ジョブは、保存すると確認待ちへ戻る
        （「直前の計画に戻る」）。直前の計画が無い失敗ジョブ・実行中は保存できない。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.result is None:
                return None
            if job.status not in (STATUS_SUCCEEDED, STATUS_FAILED):
                return None
            job.status = STATUS_SUCCEEDED
            job.error = None
            job.result = {"title": title, "body": body}
            job.updated_at = _now()
            self._save()
            return job

    def mark_succeeded(self, job_id: str, title: str, body: str) -> PlanJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = STATUS_SUCCEEDED
            job.result = {"title": title, "body": body}
            job.error = None
            job.pending_instruction = None
            job.version += 1
            job.updated_at = _now()
            self._save()
            return job

    def mark_failed(self, job_id: str, code: str, message: str) -> PlanJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = STATUS_FAILED
            job.error = {"code": code, "message": message}
            job.pending_instruction = None
            job.updated_at = _now()
            self._save()
            return job

    def delete(self, job_id: str) -> bool:
        with self._lock:
            if self._jobs.pop(job_id, None) is None:
                return False
            self._save()
            return True

    def prune_inbox(self, repo: str, open_inbox_numbers: set[int]) -> list[str]:
        """inbox項目がOPENのinboxでなくなったジョブを破棄する。削除したジョブIDを返す。

        実行中（queued/running）のジョブは完了を待ってから破棄する（次回以降のポーリングで
        完了状態になったときに削除される）。新規タスク由来（inbox番号なし）は対象外。
        """
        with self._lock:
            targets = [
                j.id
                for j in self._jobs.values()
                if j.repo == repo
                and j.inbox_issue_number is not None
                and j.inbox_issue_number not in open_inbox_numbers
                and j.status in (STATUS_SUCCEEDED, STATUS_FAILED)
            ]
            for job_id in targets:
                del self._jobs[job_id]
            if targets:
                self._save()
            return targets
