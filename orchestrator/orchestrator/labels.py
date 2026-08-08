"""GitHub issueラベルによる状態遷移の共通ユーティリティ。

仕様: docs/basic-design.md 1章（データモデル・状態遷移設計）
オーケストレータ・Agent Runner双方から利用する。
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable

STATUS_TODO = "status:todo"
STATUS_IN_PROGRESS = "status:in-progress"
STATUS_NEEDS_HUMAN_DECISION = "needs-human-decision"
STATUS_IN_REVIEW = "status:in-review"
STATUS_CLOSED = "status:closed"

# 状態は常にこの5つのうちいずれか1つのみが付与される
# （docs/basic-design.md 1章「状態一覧・遷移条件・ラベル操作」）。
STATUS_LABELS = frozenset(
    {
        STATUS_TODO,
        STATUS_IN_PROGRESS,
        STATUS_NEEDS_HUMAN_DECISION,
        STATUS_IN_REVIEW,
        STATUS_CLOSED,
    }
)

# STATUS_CLOSEDを除く、issueが着手済み（producer-deskの管理対象）であることを示す
# 4つのラベル。close_watcher.pyがクローズ検知時に「元々管理していたissueか」を
# 判定するために使う（docs/basic-design.md 1章「管理対象外issueの扱い」）。
ACTIVE_STATUS_LABELS = STATUS_LABELS - {STATUS_CLOSED}

# 自由記述指示（approve/instruct）送信時の、現在の状態ラベルに応じた遷移先
# （docs/basic-design.md 1章「自由記述指示によるラベル遷移ルール」の表）。
INSTRUCTION_TRANSITIONS: dict[str, str] = {
    STATUS_TODO: STATUS_IN_PROGRESS,
    STATUS_NEEDS_HUMAN_DECISION: STATUS_IN_PROGRESS,
    STATUS_IN_PROGRESS: STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW: STATUS_IN_REVIEW,
    STATUS_CLOSED: STATUS_IN_PROGRESS,
}

GetLabelsFn = Callable[[str, int], set[str]]
AddLabelFn = Callable[[str, int, str], None]
RemoveLabelFn = Callable[[str, int, str], None]


def gh_get_labels(repo: str, issue_number: int) -> set[str]:
    """`gh issue view --json labels` でissueに付与済みのラベル名一覧を取得する。"""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "labels"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return {label["name"] for label in data.get("labels", [])}


def gh_add_label(repo: str, issue_number: int, label: str) -> None:
    subprocess.run(
        ["gh", "issue", "edit", str(issue_number), "--repo", repo, "--add-label", label],
        check=True,
    )


def gh_remove_label(repo: str, issue_number: int, label: str) -> None:
    subprocess.run(
        ["gh", "issue", "edit", str(issue_number), "--repo", repo, "--remove-label", label],
        check=True,
    )


def transition_label(
    repo: str,
    issue_number: int,
    new_label: str,
    *,
    get_labels: GetLabelsFn = gh_get_labels,
    add_label: AddLabelFn = gh_add_label,
    remove_label: RemoveLabelFn = gh_remove_label,
) -> None:
    """issueの状態ラベルを`new_label`に冪等に遷移させる。

    現在のラベル一覧を取得してから差分のみ適用するため、途中で失敗しても
    再実行すれば収束する（docs/basic-design.md 1章「冪等な状態遷移フロー」）。
    """
    current_labels = get_labels(repo, issue_number)

    if new_label in current_labels:
        return

    for label in current_labels & STATUS_LABELS:
        remove_label(repo, issue_number, label)

    add_label(repo, issue_number, new_label)


def resolve_instruction_label(current_labels: Iterable[str]) -> str:
    """自由記述指示（approve/instruct）送信時の遷移先ラベルを決定する。

    現在の状態ラベルが5つのいずれでもない場合（本来発生しない想定）は、
    未着手として扱い `status:in-progress` への遷移とする。
    """
    current_status = next((label for label in current_labels if label in STATUS_LABELS), None)
    if current_status is None:
        return STATUS_IN_PROGRESS
    return INSTRUCTION_TRANSITIONS[current_status]
