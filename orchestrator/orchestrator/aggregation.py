"""複数プロジェクトのissueをダッシュボード表示用に集約する。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））
- 判断待ち一覧: `needs-human-decision` ラベル付きissueを横断集約
- レビュー待ち一覧: `status:in-review` ラベル付きissueを横断集約（issue #58）
- 活動ログ（タイムライン）: 各issueの `updatedAt` とラベル遷移をイベントとして時系列に並べる
  （5つの状態ラベルのいずれも付与されていない管理対象外issueは除外する。
  docs/basic-design.md 1章「管理対象外issueの扱い」）
- 孤立したin-progress検知: `status:in-progress` ラベルが付いているのに、対応する
  Agent Runnerがディスパッチキュー上で実行中でも待機中でもないissueを異常として
  イベントにマークする（issue #50）
- 状態別件数: 「プロジェクトの並行状況」ウィジェット向けに、OPEN issueを状態ラベル別
  （5つの状態ラベルいずれも無し＝タグなしを含む）に集計する。`status:closed`は含めない
  （issue #115）
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from orchestrator.labels import (
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_LABEL_PRIORITY,
    STATUS_LABELS,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)

logger = logging.getLogger(__name__)

# 状態別件数（status_counts）のキーのうち、5つの状態ラベルのいずれも付与されていない
# 「タグなし」issueを表す特別なキー。実在のGitHubラベル名と衝突しないよう名前空間を
# 分ける（issue #115、ラベル付け漏れ検知用途）。
STATUS_COUNT_UNTAGGED = "untagged"

# status_countsで集計する対象（完了=status:closedは含めない。docs/basic-design.md参照）。
STATUS_COUNT_KEYS: tuple[str, ...] = (
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_IN_REVIEW,
    STATUS_COUNT_UNTAGGED,
)

# `DispatchQueue.is_active(repo, issue_number)` と同じシグネチャの関数型。
# aggregationはDispatchQueueそのものに依存せず、この関数を注入させることで
# orchestrator.dispatch_queueへの依存を避ける（他のFn型と同様の方針）。
IsDispatchActiveFn = Callable[[str, int], bool]


@dataclass
class IssueSummary:
    repo: str
    number: int
    title: str
    labels: list[str]
    comments: list[dict]
    updated_at: str
    state: str = "OPEN"
    # `status:in-review` のissueについてのみ、ポーリング時に紐づくPR番号を解決して埋める
    # （orchestrator.polling.poll_once参照、issue #58）。
    pr_number: int | None = None


@dataclass
class ActivityEvent:
    repo: str
    number: int
    title: str
    label: str
    updated_at: str
    # `label`が`status:in-progress`で、かつ対応するAgent Runnerがディスパッチキュー上
    # で実行中・待機中のいずれでもない場合にTrueになる（issue #50）。
    is_orphaned: bool = False


@dataclass
class AggregatedState:
    decisions: list[IssueSummary] = field(default_factory=list)
    reviews: list[IssueSummary] = field(default_factory=list)
    activity: list[ActivityEvent] = field(default_factory=list)
    # 状態別のOPEN issue件数（`STATUS_COUNT_UNTAGGED`含む5種、`status:closed`は含まない。
    # issue #115、「プロジェクトの並行状況」ウィジェットの件数表示用）。
    status_counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(STATUS_COUNT_KEYS, 0)
    )


def _current_status_label(issue: IssueSummary) -> str | None:
    """issueに付与された状態ラベルのうち、表示に採用する1つを決定する。

    `issue.labels`（gh CLIが返す任意の順序）の先頭一致に依存すると、状態ラベルが
    一時的に複数付与された際に`reviews`（membership check）と食い違う表示になる
    （issue #77）。`STATUS_LABEL_PRIORITY`に基づき順序に依存しない決定的な優先順位
    で解決し、複数共存を検知した場合は警告ログを出す。
    """
    present = [label for label in issue.labels if label in STATUS_LABELS]
    if len(present) > 1:
        logger.warning(
            "issue %s#%s に複数の状態ラベルが同時に付与されています: %s "
            "(優先順位: %s に基づき解決します)",
            issue.repo,
            issue.number,
            sorted(present),
            STATUS_LABEL_PRIORITY,
        )
    return next((label for label in STATUS_LABEL_PRIORITY if label in present), None)


def _is_orphaned_in_progress(
    issue: IssueSummary, label: str, is_dispatch_active: IsDispatchActiveFn | None
) -> bool:
    """`status:in-progress`のissueなのにディスパッチキュー上で動いていないかを判定する。

    `is_dispatch_active`が渡されない場合（テスト・呼び出し元がディスパッチ状態を
    持たない場合）は判定不能として常にFalseを返す（誤検知を避ける）。
    """
    if is_dispatch_active is None or label != STATUS_IN_PROGRESS:
        return False
    return not is_dispatch_active(issue.repo, issue.number)


def aggregate(
    issues_by_repo: dict[str, list[IssueSummary]],
    is_dispatch_active: IsDispatchActiveFn | None = None,
) -> AggregatedState:
    """リポジトリ別のissue一覧を、判断待ち一覧・レビュー待ち一覧・活動ログに集約する。

    `is_dispatch_active`（`DispatchQueue.is_active`、issue #50）を渡すと、活動ログの
    各イベントに孤立したin-progressの検知結果（`ActivityEvent.is_orphaned`）を含める。
    """
    all_issues = [issue for issues in issues_by_repo.values() for issue in issues]

    decisions = [issue for issue in all_issues if STATUS_NEEDS_HUMAN_DECISION in issue.labels]
    decisions.sort(key=lambda issue: issue.updated_at, reverse=True)

    reviews = [issue for issue in all_issues if STATUS_IN_REVIEW in issue.labels]
    reviews.sort(key=lambda issue: issue.updated_at, reverse=True)

    activity = [
        ActivityEvent(
            repo=issue.repo,
            number=issue.number,
            title=issue.title,
            label=label,
            updated_at=issue.updated_at,
            is_orphaned=_is_orphaned_in_progress(issue, label, is_dispatch_active),
        )
        for issue in all_issues
        if (label := _current_status_label(issue)) is not None
    ]
    activity.sort(key=lambda event: event.updated_at, reverse=True)

    status_counts = dict.fromkeys(STATUS_COUNT_KEYS, 0)
    for issue in all_issues:
        if issue.state != "OPEN":
            continue
        label = _current_status_label(issue) or STATUS_COUNT_UNTAGGED
        if label in status_counts:
            status_counts[label] += 1

    return AggregatedState(
        decisions=decisions, reviews=reviews, activity=activity, status_counts=status_counts
    )
