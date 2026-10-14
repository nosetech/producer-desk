"""指示の処理状態チェック（診断）と再実行（issue #215）。

仕様: docs/basic-design.md 2-3「処理状態チェック・再実行API」
HTTPに依存しないビジネスロジックとして実装し、server.pyから呼び出す。

オーケストレータ停止・ポーリング取りこぼし・Agent Runner異常終了等で指示が処理
されなかった場合に、issueへ指示を書き直さずに復旧できるようにする。

「最後の未処理指示」は、最後の「オーケストレータ／Agent Runner自身の区切りコメント」
（`BOUNDARY_PREFIXES`で始まる本文）より後に付いたコメントの最後の1件とする。
ダッシュボード経由の指示もポーリング検知される直接コメントも`BOT_COMMENT_MARKER`
の有無で区別できない（ダッシュボード経由は`post_comment`がマーカーを付与する）ため、
マーカーの有無は問わない。コメントが1件も無いissueは検知しない（issue本文は指示として
扱わない）。候補が指示ではないコメントの可能性があるため、UIで文面を確認させる。
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Literal

from orchestrator.aggregation import IssueSummary
from orchestrator.close_watcher import CLOSED_STATE
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import BOT_COMMENT_MARKER, PostCommentFn
from orchestrator.instruct import OnStageFn, _noop_on_stage, apply_instruction
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_LABELS,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
)

DispatchState = Literal[
    "running", "queued", "completed", "not_dispatched", "orphaned_in_progress", "not_managed"
]

# 指示ではなく処理の区切りとみなすコメントの先頭文字列。Agent Runnerの実行結果・
# 起動エラー・セッションリセット通知（agent_runner.py）と、本機能の再実行記録。
REDISPATCH_COMMENT = ":repeat: ダッシュボードから再実行しました"
BOUNDARY_PREFIXES = (
    "Agent Runner実行結果:",
    ":warning:",
    ":arrows_counterclockwise:",
    REDISPATCH_COMMENT,
)

logger = logging.getLogger(__name__)

NO_PENDING_MESSAGE = "未処理の指示コメントがありません"


class RedispatchConflictError(RuntimeError):
    """実行中・待機中のissueへの再実行時に送出する（二重実行防止）。"""


class NoPendingInstructionError(RuntimeError):
    """再実行対象の未処理指示が無い場合に送出する。"""


class IssueNotFoundError(LookupError):
    """対象issueが取得できない場合に送出する。"""


class IssueNotManagedError(ValueError):
    """状態ラベルが無い・クローズ済み等、再実行の対象外のissueに送出する。"""


@dataclass
class DispatchStatus:
    state: DispatchState
    label: str | None
    redispatchable: bool
    pending_message: str | None
    pending_comment_id: str | None
    detail: str


def _is_boundary(body: str) -> bool:
    return body.lstrip().startswith(BOUNDARY_PREFIXES)


def find_pending_instruction(comments: list[dict]) -> dict | None:
    """最後の区切りコメントより後のコメントのうち、最後の1件を返す。"""
    last_boundary = -1
    for index, comment in enumerate(comments):
        if _is_boundary(comment.get("body", "")):
            last_boundary = index
    candidates = comments[last_boundary + 1 :]
    return candidates[-1] if candidates else None


def _strip_marker(body: str) -> str:
    return body.replace(BOT_COMMENT_MARKER, "").strip()


def _state_label(labels: list[str]) -> str | None:
    found = sorted(set(labels) & STATUS_LABELS)
    return found[0] if found else None


def diagnose(issue: IssueSummary, dispatch_queue: DispatchQueue) -> DispatchStatus:
    label = _state_label(issue.labels)
    if issue.state == CLOSED_STATE or label is None:
        return DispatchStatus(
            state="not_managed",
            label=label,
            redispatchable=False,
            pending_message=None,
            pending_comment_id=None,
            detail="producer-deskの管理対象外（状態ラベルなし・クローズ済み）のissueです",
        )

    if dispatch_queue.is_active(issue.repo, issue.number):
        running = dispatch_queue.is_current(issue.repo, issue.number)
        return DispatchStatus(
            state="running" if running else "queued",
            label=label,
            redispatchable=False,
            pending_message=None,
            pending_comment_id=None,
            detail="Agent Runnerが実行中です" if running else "実行待ちのキューに入っています",
        )

    pending = find_pending_instruction(issue.comments)
    message = _strip_marker(pending["body"]) if pending else None
    if message == "":
        pending, message = None, None
    comment_id = pending["id"] if pending else None

    if label == STATUS_IN_PROGRESS:
        return DispatchStatus(
            state="orphaned_in_progress",
            label=label,
            redispatchable=message is not None,
            pending_message=message,
            pending_comment_id=comment_id,
            detail="status:in-progressですが実行中・待機中ではありません",
        )
    if message is not None:
        return DispatchStatus(
            state="not_dispatched",
            label=label,
            redispatchable=True,
            pending_message=message,
            pending_comment_id=comment_id,
            detail="処理された形跡のない指示コメントがあります",
        )
    return DispatchStatus(
        state="completed",
        label=label,
        redispatchable=False,
        pending_message=None,
        pending_comment_id=None,
        detail=NO_PENDING_MESSAGE,
    )


def find_issue(issues: list[IssueSummary], issue_number: int) -> IssueSummary:
    for issue in issues:
        if issue.number == issue_number:
            return issue
    raise IssueNotFoundError(f"issue #{issue_number} が見つかりません")


def handle_redispatch(
    issue: IssueSummary,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    post_comment: PostCommentFn,
    dispatch_queue: DispatchQueue,
    on_stage: OnStageFn = _noop_on_stage,
) -> DispatchStatus:
    """未処理の指示を、issueへ新規コメントを投稿せずにキューへ再投入する。

    ラベル整合・キュー投入は`instruct.apply_instruction`を共有する。再実行の事実のみ
    botマーカー付きコメントで記録する（指示として再検知されない）。
    """
    status = diagnose(issue, dispatch_queue)
    if status.state == "not_managed":
        raise IssueNotManagedError(status.detail)
    if status.state in ("running", "queued"):
        raise RedispatchConflictError(
            f"{issue.repo}#{issue.number} は{status.detail}。再実行できません"
        )
    if status.pending_message is None:
        raise NoPendingInstructionError(NO_PENDING_MESSAGE)

    apply_instruction(
        issue.repo,
        issue.number,
        status.pending_message,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
        dispatch_queue=dispatch_queue,
        on_stage=on_stage,
    )
    # 記録コメントは付随処理のため、失敗してもキュー投入済みの再実行自体は成功扱いにする。
    try:
        post_comment(issue.repo, issue.number, REDISPATCH_COMMENT)
        on_stage("comment")
    except subprocess.CalledProcessError as e:
        logger.warning(
            "%s#%s の再実行記録コメント投稿に失敗しました: %s", issue.repo, issue.number, e
        )
    return status
