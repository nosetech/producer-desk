"""CI完了待機中のissueをポーリングで検知し、CI完了後にAgent Runnerを自動再開するフロー。

仕様: issue #173（issue #152/#153で「AIが能動的にneeds-human-decisionを選ぶ経路」を
塞いだ後も、「CI待ちで意図通り正常終了 → run_agent_runnerの強制フォールバック安全網
（issue #78由来）がラベル遷移漏れと区別できず無条件発動」という別経路で同じ症状
（CI待ち中に判断待ちへ落ちる）が再発した）。

Agent Runnerは、CI完了待ちのためにセッションを意図的に終了する際、最終応答に
`agent_runner.CI_WAIT_MARKER_PREFIX`で始まる機械可読マーカー（対象PR番号を含む）を
埋め込む（`agent_runner.AGENT_RUNNER_LABEL_INSTRUCTION`）。この最終応答は
`run_agent_runner`によってissueコメントとしてそのまま投稿される
（`github_client.BOT_COMMENT_MARKER`付き）ため、本モジュールはポーリングのたびに
各issueの最新コメントを確認し、
- status:in-progressのまま、最新コメントにマーカーが付いている
  → 対象PRのCIステータス（`get_pr_status_check_rollup`）を確認する
  - 完了していれば`dispatch_queue`経由でAgent Runnerをresumeし後続処理を継続させる
  - 未完了ならそのまま待つ（次回ポーリングで再確認）
- マーカー検出からの経過時間が`CI_WAIT_TIMEOUT`を超えても完了しなければ、無限待機を
  避けるフェイルセーフとして`needs-human-decision`へ遷移させる
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from orchestrator.agent_runner import extract_ci_wait_marker
from orchestrator.aggregation import IssueSummary
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import BOT_COMMENT_MARKER, GetPrStatusCheckRollupFn, PostCommentFn
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_NEEDS_HUMAN_DECISION,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    transition_label,
)

NowFn = Callable[[], datetime]

# 無限待機の防止（修正方針5）。オーケストレータ自身のポーリングにも上限を設け、
# それでも完了しなければ初めてneeds-human-decisionへ遷移させるフェイルセーフとする。
CI_WAIT_TIMEOUT = timedelta(hours=6)

CI_COMPLETED_RESUME_MESSAGE = (
    "CIが完了しました。statusCheckRollupの結果を確認し、後続の対応"
    "（レビュー結果の確認・必要な修正・レビュー結果のPRへのコメント投稿・"
    "状態ラベルの遷移判断）を継続してください。"
)


def _is_check_pending(check: dict) -> bool:
    """GitHub Checks API（`status`）・レガシーCommit Status API（`state`）双方に対応する。

    `status`（CheckRun）が存在すれば`COMPLETED`以外を待機中とみなし、無ければ
    `state`（StatusContext）が`PENDING`かどうかで判定する（`github_client.
    get_pr_status_check_rollup`のdocstring参照）。
    """
    status = check.get("status")
    if status is not None:
        return status != "COMPLETED"
    return check.get("state") == "PENDING"


@dataclass
class _WaitState:
    pr_number: int
    first_seen: datetime


class CiWaitTracker:
    """issueごとのCI待機開始時刻を記録する（`CI_WAIT_TIMEOUT`判定用）。

    プロセス内メモリのみで保持する（オーケストレータ再起動でリセットされるが、
    再起動後の最初のポーリングで改めて`first_seen`が記録され直すだけであり、
    「無限待機を避ける」というフェイルセーフの目的上は問題ない）。
    """

    def __init__(self) -> None:
        self._waiting: dict[tuple[str, int], _WaitState] = {}

    def observe(self, repo: str, issue_number: int, pr_number: int, *, now: datetime) -> _WaitState:
        key = (repo, issue_number)
        state = self._waiting.get(key)
        if state is None or state.pr_number != pr_number:
            state = _WaitState(pr_number=pr_number, first_seen=now)
            self._waiting[key] = state
        return state

    def clear(self, repo: str, issue_number: int) -> None:
        self._waiting.pop((repo, issue_number), None)


def _latest_ci_wait_pr_number(issue: IssueSummary) -> int | None:
    """issueの最新コメントがCI待機マーカー付きのAgent Runner投稿であれば対象PR番号を返す。

    最新コメントのみを見る。CI待機後に別の（マーカーの無い）コメントが追加されて
    いれば、そのCI待機は既に解消済み（後続処理が進んだ、または人間が介入した）と
    みなせるため。
    """
    if not issue.comments:
        return None
    latest = issue.comments[-1]
    body = latest.get("body", "")
    if BOT_COMMENT_MARKER not in body:
        return None
    return extract_ci_wait_marker(body)


def process_ci_waiting_issues(
    issues_by_repo: dict[str, list[IssueSummary]],
    tracker: CiWaitTracker,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    get_pr_status_check_rollup: GetPrStatusCheckRollupFn,
    dispatch_queue: DispatchQueue,
    post_comment: PostCommentFn,
    now: NowFn = lambda: datetime.now(UTC),
) -> None:
    for repo, issues in issues_by_repo.items():
        for issue in issues:
            if STATUS_IN_PROGRESS not in issue.labels:
                tracker.clear(repo, issue.number)
                continue

            pr_number = _latest_ci_wait_pr_number(issue)
            if pr_number is None:
                tracker.clear(repo, issue.number)
                continue

            if dispatch_queue.is_active(repo, issue.number):
                # 既に（前回ポーリングでのresumeも含め）ディスパッチ中のため、
                # 二重ディスパッチを避けてこの周回はスキップする。
                continue

            current_time = now()
            state = tracker.observe(repo, issue.number, pr_number, now=current_time)

            checks = get_pr_status_check_rollup(repo, pr_number)
            if any(_is_check_pending(check) for check in checks):
                if current_time - state.first_seen >= CI_WAIT_TIMEOUT:
                    timeout_hours = int(CI_WAIT_TIMEOUT.total_seconds() // 3600)
                    post_comment(
                        repo,
                        issue.number,
                        f":warning: PR #{pr_number}のCI完了待機が{timeout_hours}時間を"
                        "超えたため、needs-human-decisionへ遷移します。CIの状況を"
                        "確認してください。",
                    )
                    transition_label(
                        repo,
                        issue.number,
                        STATUS_NEEDS_HUMAN_DECISION,
                        get_labels=get_labels,
                        add_label=add_label,
                        remove_label=remove_label,
                    )
                    tracker.clear(repo, issue.number)
                continue

            tracker.clear(repo, issue.number)
            dispatch_queue.enqueue(repo, issue.number, CI_COMPLETED_RESUME_MESSAGE)
