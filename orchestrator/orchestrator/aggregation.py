"""複数プロジェクトのissueをダッシュボード表示用に集約する。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））
- 判断待ち一覧: `needs-human-decision` ラベル付きissueを横断集約
- レビュー待ち一覧: `status:in-review` ラベル付きissueを横断集約（issue #58）
- 活動ログ（タイムライン）: 各issueの `updatedAt` とラベル遷移をイベントとして時系列に並べる
  （5つの状態ラベルのいずれも付与されていない管理対象外issueは除外する。
  docs/basic-design.md 1章「管理対象外issueの扱い」）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from orchestrator.labels import (
    STATUS_IN_REVIEW,
    STATUS_LABEL_PRIORITY,
    STATUS_LABELS,
    STATUS_NEEDS_HUMAN_DECISION,
)

logger = logging.getLogger(__name__)


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


@dataclass
class AggregatedState:
    decisions: list[IssueSummary] = field(default_factory=list)
    reviews: list[IssueSummary] = field(default_factory=list)
    activity: list[ActivityEvent] = field(default_factory=list)


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


def aggregate(issues_by_repo: dict[str, list[IssueSummary]]) -> AggregatedState:
    """リポジトリ別のissue一覧を、判断待ち一覧・レビュー待ち一覧・活動ログに集約する。"""
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
        )
        for issue in all_issues
        if (label := _current_status_label(issue)) is not None
    ]
    activity.sort(key=lambda event: event.updated_at, reverse=True)

    return AggregatedState(decisions=decisions, reviews=reviews, activity=activity)
