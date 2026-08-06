"""issueがGitHub上でクローズされたことをポーリングで検知し、`status:closed`へ
遷移させるフロー。

仕様: docs/basic-design.md 1章「状態一覧・遷移条件・ラベル操作」・
2-2（データ取得仕様（ポーリング））

issueのクローズ操作自体（人間による手動クローズ、PRマージに伴う`Closes #<issue番号>`
経由の自動クローズいずれも）はproducer-deskの外側で起きるため、Agent Runnerの自己付与
ラベル（needs-human-decision・status:in-review）とは異なり、クローズをトリガーに
できるアクターがオーケストレータ自身しかいない。次回ポーリングで検知し、`status:closed`
を自己付与する。

対象は`ACTIVE_STATUS_LABELS`（status:todo/status:in-progress/needs-human-decision/
status:in-review）のいずれかが付与済み＝producer-deskが一度でも管理していたissueのみ。
一度も状態ラベルが付いていない管理対象外issueがクローズされても何もしない
（docs/basic-design.md 1章「管理対象外issueの扱い」）。
"""

from __future__ import annotations

from orchestrator.aggregation import IssueSummary
from orchestrator.labels import (
    ACTIVE_STATUS_LABELS,
    STATUS_CLOSED,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
    transition_label,
)

CLOSED_STATE = "CLOSED"


def close_finished_issues(
    issues_by_repo: dict[str, list[IssueSummary]],
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
) -> None:
    for repo, issues in issues_by_repo.items():
        for issue in issues:
            if issue.state != CLOSED_STATE:
                continue
            if not (set(issue.labels) & ACTIVE_STATUS_LABELS):
                continue

            transition_label(
                repo,
                issue.number,
                STATUS_CLOSED,
                get_labels=get_labels,
                add_label=add_label,
                remove_label=remove_label,
            )
