"""複数プロジェクトのissueをダッシュボード表示用に集約する。

仕様: docs/basic-design.md 2-2（データ取得仕様（ポーリング））
- 判断待ち一覧: `needs-human-decision` ラベル付きissueを横断集約
- レビュー待ち一覧: `status:in-review` ラベル付きissueを横断集約（issue #58）
- プロジェクト状況: 「プロジェクトの並行状況」ウィジェット向けに、プロジェクト（リポジトリ）
  ごとの直近更新issueの状態ラベル・状態別件数（5つの状態ラベルいずれも無し＝タグなしを
  含む。`status:closed`は含めない）・孤立したin-progress検知結果を集計する
  （issue #50, #115。かつては横断タイムライン「活動ログ」がこれらの情報源だったが、
  issue #121でタイムライン自体を廃止しプロジェクト単位の集計に一本化した）
- 孤立したin-progress検知: `status:in-progress` ラベルが付いているのに、対応する
  Agent Runnerがディスパッチキュー上で実行中でも待機中でもないissueを異常として
  `ProjectStatus.is_orphaned` にマークする（issue #50）
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
class ProjectStatus:
    """プロジェクト（リポジトリ）単位の「並行状況」ウィジェット向け集計（issue #121）。

    ダッシュボードの`activity`（横断タイムライン、issue #121で廃止）には依存せず、
    リポジトリごとのissue一覧から直接算出する。
    """

    repo: str
    # 直近更新issueの状態ラベル。そのリポジトリに5つの状態ラベルいずれかを持つissueが
    # 1件も無い場合はNone（管理対象issueが存在しない）。
    label: str | None = None
    number: int | None = None
    title: str | None = None
    # `label`が`status:in-progress`で、かつ対応するAgent Runnerがディスパッチキュー上
    # で実行中・待機中のいずれでもない場合にTrueになる（issue #50）。
    is_orphaned: bool = False
    # 状態別のOPEN issue件数（`STATUS_COUNT_UNTAGGED`含む5種、`status:closed`は含まない）。
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(STATUS_COUNT_KEYS, 0))


@dataclass
class AggregatedState:
    decisions: list[IssueSummary] = field(default_factory=list)
    reviews: list[IssueSummary] = field(default_factory=list)
    # プロジェクト（リポジトリ）単位の並行状況集計（issue #121）。
    project_status: list[ProjectStatus] = field(default_factory=list)
    # 状態別のOPEN issue件数（`STATUS_COUNT_UNTAGGED`含む5種、`status:closed`は含まない。
    # issue #115、全プロジェクト横断の合計値）。
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
    """リポジトリ別のissue一覧を、判断待ち一覧・レビュー待ち一覧・プロジェクト状況に集約する。

    `is_dispatch_active`（`DispatchQueue.is_active`、issue #50）を渡すと、プロジェクト
    状況の各要素に孤立したin-progressの検知結果（`ProjectStatus.is_orphaned`）を含める。
    """
    all_issues = [issue for issues in issues_by_repo.values() for issue in issues]

    decisions = [issue for issue in all_issues if STATUS_NEEDS_HUMAN_DECISION in issue.labels]
    decisions.sort(key=lambda issue: issue.updated_at, reverse=True)

    reviews = [issue for issue in all_issues if STATUS_IN_REVIEW in issue.labels]
    reviews.sort(key=lambda issue: issue.updated_at, reverse=True)

    status_counts = dict.fromkeys(STATUS_COUNT_KEYS, 0)
    project_status: list[ProjectStatus] = []

    for repo, issues in issues_by_repo.items():
        labeled: list[tuple[IssueSummary, str]] = []
        repo_counts = dict.fromkeys(STATUS_COUNT_KEYS, 0)

        for issue in issues:
            label = _current_status_label(issue)
            if label is not None:
                labeled.append((issue, label))
            if issue.state == "OPEN":
                count_key = label or STATUS_COUNT_UNTAGGED
                if count_key in repo_counts:
                    repo_counts[count_key] += 1
                    status_counts[count_key] += 1

        if not labeled:
            project_status.append(ProjectStatus(repo=repo, counts=repo_counts))
            continue

        latest_issue, latest_label = max(labeled, key=lambda pair: pair[0].updated_at)
        project_status.append(
            ProjectStatus(
                repo=repo,
                label=latest_label,
                number=latest_issue.number,
                title=latest_issue.title,
                is_orphaned=_is_orphaned_in_progress(
                    latest_issue, latest_label, is_dispatch_active
                ),
                counts=repo_counts,
            )
        )

    return AggregatedState(
        decisions=decisions,
        reviews=reviews,
        project_status=project_status,
        status_counts=status_counts,
    )
