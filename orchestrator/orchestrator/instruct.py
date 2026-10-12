"""ダッシュボードからの指示（承認/自由記述/新規タスク作成）を処理する。

仕様: docs/basic-design.md 2-3（指示出しAPI）・5-3（内部処理フロー）
HTTPに依存しないビジネスロジックとして実装し、server.pyから呼び出す。
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from orchestrator.aggregation import PrCandidate
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import (
    CloseIssueFn,
    CreateIssueFn,
    DeleteBranchFn,
    GetPrBranchFn,
    ListLinkedPrsFn,
    MergePrFn,
    PostCommentFn,
)
from orchestrator.github_client import close_issue as gh_close_issue
from orchestrator.github_client import delete_branch as gh_delete_branch
from orchestrator.github_client import get_pr_branch as gh_get_pr_branch
from orchestrator.github_client import list_linked_prs as gh_list_linked_prs
from orchestrator.github_client import merge_pr as gh_merge_pr
from orchestrator.labels import (
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_TODO,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    resolve_instruction_label,
    transition_label,
)
from orchestrator.prompts import PromptSpec, load_prompt_text
from orchestrator.worktree import SyncWorktreeFn
from orchestrator.worktree import sync_worktree_after_branch_delete as gh_sync_worktree

APPROVE_DEFAULT_MESSAGE = "承認します。進めてください。"

# issue #149: 判断待ちの承認時（ダッシュボードの承認はmessageを持たない）に、issue
# コメントとして投稿される定型文。Agent Runnerへの指示としてそのまま渡るため、
# 他のプロンプトと同様ダッシュボードから編集できるようにする
# （必須トークン・プレースホルダは無し）。
APPROVE_DEFAULT_MESSAGE_SPEC = PromptSpec(
    key="approve_default_message",
    title="判断待ち承認時の定型コメント",
    description=(
        "判断待ち（needs-human-decision）のissueを承認したときにissueへ投稿される"
        "定型文。レビュー待ち（status:in-review）の承認ではコメントは投稿されず、"
        "PRのマージのみが行われるため、この文言は使われない"
    ),
    default=APPROVE_DEFAULT_MESSAGE,
    placeholders=(),  # issueコメントとしてそのまま投稿され、展開されない
)

logger = logging.getLogger(__name__)

Action = Literal["approve", "instruct"]
Dispatch = Literal["immediate", "queued"]

# ダッシュボードの段階表示（ComposerBar/DecisionCard/ReviewCard）向けに、処理の
# 進み具合を1ステップ完了するたびに通知するコールバック。`stage`は"comment"/
# "label"/"issue"/"dispatch"/"merge"/"close"/"branch_delete"/"worktree_sync"の
# いずれか（server.pyのProgressStoreがこれをそのままポーリングレスポンスに詰める）。
# ブランチ削除・worktree同期は失敗しても処理全体は成功扱いになるため、その場合は
# 成功時と区別できるよう`${stage}_skipped`を通知する。
# comment_watcher.py等、ダッシュボード操作を経由しない呼び出し元ではデフォルトの
# no-opのまま使われる。
OnStageFn = Callable[[str], None]


def _noop_on_stage(stage: str) -> None:
    pass


class ReviewMergeError(RuntimeError):
    """レビュー承認時、対象issueに紐づくPRが見つからない場合に送出する（issue #58）。"""


class PrSelectionRequiredError(RuntimeError):
    """レビュー承認時、対応PRを一意に特定できずユーザーの選択が必要な場合に送出する（issue #206）。

    候補が2件以上ある場合に、誤ったPRを自動マージしないために使う。`candidates`は
    ダッシュボードの選択UIに返す現在の候補一覧。
    """

    def __init__(self, message: str, candidates: list[PrCandidate]) -> None:
        super().__init__(message)
        self.candidates = candidates


class InvalidPrSelectionError(ValueError):
    """承認リクエストの`prNumber`が現在の候補に含まれない場合に送出する（issue #206）。"""


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
    on_stage: OnStageFn = _noop_on_stage,
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
    on_stage("label")
    dispatch_queue.enqueue(repo, issue_number, message)
    on_stage("dispatch")
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
    list_linked_prs: ListLinkedPrsFn = gh_list_linked_prs,
    merge_pr: MergePrFn = gh_merge_pr,
    close_issue: CloseIssueFn = gh_close_issue,
    get_pr_branch: GetPrBranchFn = gh_get_pr_branch,
    delete_branch: DeleteBranchFn = gh_delete_branch,
    worktree_path: str | None = None,
    sync_worktree: SyncWorktreeFn = gh_sync_worktree,
    on_stage: OnStageFn = _noop_on_stage,
    pr_number: int | None = None,
) -> InstructResult:
    if action == "approve" and STATUS_IN_REVIEW in get_labels(repo, issue_number):
        # レビュー待ちの承認は「コメント投稿→ラベル遷移→ディスパッチ」経路には乗せず、
        # 紐づくPRのsquash mergeのみを行う（issue #58）。
        # PR本文の`Closes #`によるGitHubの自動クローズはデフォルトブランチへのマージ時
        # にしか発動せず、本プロジェクトのワークフロー（`develop`へマージ）では発動しないため
        # issueが開いたまま残っていた不具合が確認された。マージ成功後はここで明示的にissueを
        # クローズする。
        #
        # マージ対象は「issueをcloseする意図のOPEN PR」の候補（issue #206）から決める。
        # `pr_number`（ユーザーが選択したPR）が指定された場合は現在の候補に含まれるかを
        # 再検証し、含まれなければ拒否する（古い画面・なりすましからの誤マージ防止）。
        # 未指定で候補が一意に決まらない場合は、自動マージせずユーザーの選択を求める。
        candidates = list_linked_prs(repo, issue_number)
        if pr_number is not None:
            if pr_number not in {c.number for c in candidates}:
                raise InvalidPrSelectionError(
                    f"PR #{pr_number} は {repo}#{issue_number} の対応PR候補に含まれません"
                )
        elif not candidates:
            raise ReviewMergeError(f"{repo}#{issue_number} の対応PRが見つかりません")
        elif len(candidates) > 1:
            raise PrSelectionRequiredError(
                f"{repo}#{issue_number} の対応PR候補が複数あります。マージするPRを選択してください",
                candidates,
            )
        else:
            pr_number = candidates[0].number
        merge_pr(repo, pr_number)
        on_stage("merge")
        close_issue(repo, issue_number)
        on_stage("close")
        # ラベルもここで`status:closed`へ即時遷移させる。close_watcher.pyの背景ポーリング
        # （5分間隔）に委ねると、承認直後にserver.pyが行うStateStore同期更新（issue #70）の
        # 時点では`status:in-review`のままのため、aggregate()のreviews判定
        # （ラベルのみを見る）に引っかかり続け、カードが一覧からすぐ消えない不具合になる。
        transition_label(
            repo,
            issue_number,
            STATUS_CLOSED,
            get_labels=get_labels,
            add_label=add_label,
            remove_label=remove_label,
        )
        on_stage("label")
        # ブランチ削除はマージ・issueクローズの後始末に過ぎない（issue #72）。
        # ここで失敗（保護ブランチ設定・既に削除済み等）しても、本質的な処理である
        # マージ・issueクローズが既に成功している以上、承認自体は成功として扱う
        # （--delete-branchをマージと同一コマンドに含めた場合、ブランチ削除だけの失敗で
        # 例外が送出されclose_issueが実行されなくなる不具合の再発を避けるため、
        # あえて分離したステップにしている）。
        branch: str | None = None
        try:
            branch = get_pr_branch(repo, pr_number)
            delete_branch(repo, branch)
            on_stage("branch_delete")
        except subprocess.CalledProcessError as e:
            logger.warning(
                "%s#%s (PR #%s) のブランチ削除に失敗しました: %s", repo, issue_number, pr_number, e
            )
            branch = None
            on_stage("branch_delete_skipped")

        # worktree同期はリモートブランチ削除の後始末に過ぎない（issue #80）。実行中の
        # Agent Runnerが同じプロジェクトの別issueで動いている場合、worktreeを横から
        # 書き換えるとそのセッションを破壊するおそれがあるためスキップする。
        if branch is not None and worktree_path is not None:
            if dispatch_queue.is_running(repo):
                logger.info(
                    "%s は実行中のためworktree同期をスキップしました（対象ブランチ: %s）",
                    repo,
                    branch,
                )
                on_stage("worktree_sync_skipped")
            else:
                sync_worktree(worktree_path, branch)
                on_stage("worktree_sync")
        else:
            on_stage("worktree_sync_skipped")
        return InstructResult(action="approve", comment="", label=None, dispatched=False)

    if action == "approve":
        comment = message or load_prompt_text(APPROVE_DEFAULT_MESSAGE_SPEC)
    elif action == "instruct":
        if not message:
            raise ValueError("instructアクションにはmessageが必須です")
        comment = message
    else:
        raise ValueError(f"不明なaction: {action}")

    post_comment(repo, issue_number, comment)
    on_stage("comment")

    label = apply_instruction(
        repo,
        issue_number,
        comment,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
        dispatch_queue=dispatch_queue,
        on_stage=on_stage,
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
    on_stage: OnStageFn = _noop_on_stage,
) -> CreateIssueResult:
    if dispatch not in ("immediate", "queued"):
        raise ValueError(f"不明なdispatch: {dispatch}")

    issue_number = create_issue(repo, title, prompt)
    on_stage("issue")
    add_label(repo, issue_number, STATUS_TODO)
    on_stage("label")

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
    dispatch_queue.enqueue(repo, issue_number, prompt)
    on_stage("dispatch")
    return CreateIssueResult(issue_number=issue_number, dispatched=True)
