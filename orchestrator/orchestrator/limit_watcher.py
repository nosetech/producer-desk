"""利用リミット待ちで判断待ちになったissueを、解除予定時刻を過ぎたら自動再開する（issue #331）。

`ci_watcher`と同じ構造で、`main.py`の`on_issues_fetched`からポーリングのたびに呼ばれる。

対象は、OPENかつ`needs-human-decision`で、**最新コメント**が利用リミット待ちマーカー
（`limit_wait.LIMIT_WAIT_MARKER_PREFIX`）付きのBot投稿であるissue。マーカーの後に人間の
コメント（返信・`/model`指定）や取り消しコメントが付けば最新コメントではなくなるため、
自然に対象外になる。待機状態はコメントから毎回導けるので、オーケストレータを再起動しても
待機は失われない。

解除予定時刻＋`LIMIT_RESUME_GRACE`を過ぎたら、`status:in-progress`へ冪等に遷移させ、
`DispatchQueue`経由で同じセッションを`--resume`する。再開メッセージには連続の自動再開回数を
埋め込み、再開後にまた429になった場合は`agent_runner`がその回数を引き継ぐ
（上限に達したらマーカーを付けずに止める）。
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from orchestrator.aggregation import IssueSummary, latest_limit_wait
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_NEEDS_HUMAN_DECISION,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    transition_label,
)
from orchestrator.limit_wait import build_limit_resume_message

logger = logging.getLogger(__name__)

NowFn = Callable[[], datetime]

# 解除予定時刻ちょうどではまだリミットが戻っていないことがあるため、少し余裕を持たせる。
LIMIT_RESUME_GRACE = timedelta(minutes=3)


def process_limit_waiting_issues(
    issues_by_repo: dict[str, list[IssueSummary]],
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    dispatch_queue: DispatchQueue,
    now: NowFn = lambda: datetime.now(UTC),
    grace: timedelta = LIMIT_RESUME_GRACE,
) -> None:
    for repo, issues in issues_by_repo.items():
        for issue in issues:
            if issue.state != "OPEN" or STATUS_NEEDS_HUMAN_DECISION not in issue.labels:
                continue
            wait = latest_limit_wait(issue)
            if wait is None:
                continue
            if now() < wait.reset_at + grace:
                continue
            if dispatch_queue.is_active(repo, issue.number):
                continue

            # `gh`の失敗をポーリングループへ伝えると、バックグラウンドスレッドごと止まって
            # 全プロジェクトのポーリングが止まる（ci_watcherと同じ）。次回ポーリングで再試行する。
            try:
                transition_label(
                    repo,
                    issue.number,
                    STATUS_IN_PROGRESS,
                    get_labels=get_labels,
                    add_label=add_label,
                    remove_label=remove_label,
                )
            except subprocess.CalledProcessError:
                logger.warning(
                    "%s#%s の利用リミット待ちからの自動再開でラベル遷移に失敗しました。"
                    "次回ポーリングで再試行します。",
                    repo,
                    issue.number,
                    exc_info=True,
                )
                continue

            logger.info(
                "%s#%s: 利用リミットの解除予定時刻（%s）を過ぎたため自動再開します（%d回目）。",
                repo,
                issue.number,
                wait.reset_at.isoformat(),
                wait.attempt,
            )
            dispatch_queue.enqueue(repo, issue.number, build_limit_resume_message(wait.attempt))
