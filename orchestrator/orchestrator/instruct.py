"""ダッシュボードからの指示（承認/却下/自由記述/新規タスク作成）を処理する。

仕様: docs/basic-design.md 2-3（指示出しAPI）・5-3（内部処理フロー）
HTTPに依存しないビジネスロジックとして実装し、server.pyから呼び出す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import CreateIssueFn, PostCommentFn
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_TODO,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    resolve_instruction_label,
    transition_label,
)

APPROVE_DEFAULT_MESSAGE = "承認します。進めてください。"
REJECT_DEFAULT_MESSAGE = "却下します。"

Action = Literal["approve", "reject", "instruct"]
Dispatch = Literal["immediate", "queued"]


@dataclass
class InstructResult:
    action: Action
    comment: str
    label: str | None
    dispatched: bool


@dataclass
class CreateIssueResult:
    issue_number: int
    dispatched: bool


def apply_instruction(
    repo: str,
    issue_number: int,
    message: str,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    dispatch_queue: DispatchQueue,
) -> str:
    """自由記述指示のラベル遷移ルールに従いラベルを更新し、ディスパッチキューに投入する。

    docs/basic-design.md 1章「自由記述指示によるラベル遷移ルール」に基づき、
    `approve`/`instruct`、および直接issueにコメントされた指示（comment_watcher）の
    双方から共通で呼び出される。
    """
    current_labels = get_labels(repo, issue_number)
    new_label = resolve_instruction_label(current_labels)
    transition_label(
        repo,
        issue_number,
        new_label,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
    )
    dispatch_queue.enqueue(repo, message)
    return new_label


def handle_instruct(
    repo: str,
    issue_number: int,
    action: Action,
    message: str | None,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    post_comment: PostCommentFn,
    dispatch_queue: DispatchQueue,
) -> InstructResult:
    if action == "approve":
        comment = message or APPROVE_DEFAULT_MESSAGE
    elif action == "reject":
        comment = message or REJECT_DEFAULT_MESSAGE
    elif action == "instruct":
        if not message:
            raise ValueError("instructアクションにはmessageが必須です")
        comment = message
    else:
        raise ValueError(f"不明なaction: {action}")

    post_comment(repo, issue_number, comment)

    if action == "reject":
        # ラベルは維持し、ディスパッチも行わない（差し戻し）
        return InstructResult(action=action, comment=comment, label=None, dispatched=False)

    label = apply_instruction(
        repo,
        issue_number,
        comment,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
        dispatch_queue=dispatch_queue,
    )
    return InstructResult(action=action, comment=comment, label=label, dispatched=True)


def handle_create_issue(
    repo: str,
    title: str,
    prompt: str,
    dispatch: Dispatch,
    *,
    create_issue: CreateIssueFn,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    dispatch_queue: DispatchQueue,
) -> CreateIssueResult:
    if dispatch not in ("immediate", "queued"):
        raise ValueError(f"不明なdispatch: {dispatch}")

    issue_number = create_issue(repo, title, prompt)
    add_label(repo, issue_number, STATUS_TODO)

    if dispatch == "queued":
        return CreateIssueResult(issue_number=issue_number, dispatched=False)

    transition_label(
        repo,
        issue_number,
        STATUS_IN_PROGRESS,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
    )
    dispatch_queue.enqueue(repo, prompt)
    return CreateIssueResult(issue_number=issue_number, dispatched=True)
