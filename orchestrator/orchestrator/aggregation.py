"""複数プロジェクトのissueをダッシュボード表示用に集約する。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））
- 判断待ち一覧: `needs-human-decision` ラベル付きissueを横断集約
- 活動ログ（タイムライン）: 各issueの `updatedAt` とラベル遷移をイベントとして時系列に並べる
  （5つの状態ラベルのいずれも付与されていない管理対象外issueは除外する。
  docs/basic-design.md 1章「管理対象外issueの扱い」）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.labels import STATUS_LABELS, STATUS_NEEDS_HUMAN_DECISION


@dataclass
class IssueSummary:
    repo: str
    number: int
    title: str
    labels: list[str]
    comments: list[dict]
    updated_at: str
    state: str = "OPEN"


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
    activity: list[ActivityEvent] = field(default_factory=list)


def _current_status_label(issue: IssueSummary) -> str | None:
    return next((label for label in issue.labels if label in STATUS_LABELS), None)


def aggregate(issues_by_repo: dict[str, list[IssueSummary]]) -> AggregatedState:
    """リポジトリ別のissue一覧を、判断待ち一覧・活動ログに集約する。"""
    all_issues = [issue for issues in issues_by_repo.values() for issue in issues]

    decisions = [issue for issue in all_issues if STATUS_NEEDS_HUMAN_DECISION in issue.labels]
    decisions.sort(key=lambda issue: issue.updated_at, reverse=True)

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

    return AggregatedState(decisions=decisions, activity=activity)
