"""inbox（バグ・機能アイデアの一行メモ置き場）の作成・編集・削除（issue #288）。

仕様: docs/basic-design.md 1章（補助ラベル`inbox`）・2-3（inbox API）
inbox項目は`inbox`ラベル＋種別ラベル（bug/enhancement/other）1つを持つGitHub issueで、
状態ラベルは付けない（Agent Runnerに自動ディスパッチされない）。HTTPに依存しない
ビジネスロジックとして実装し、server.pyから呼び出す。
"""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.github_client import CreateIssueFn
from orchestrator.labels import (
    INBOX_KIND_LABELS,
    INBOX_LABEL,
    AddLabelFn,
    GetLabelsFn,
    RemoveLabelFn,
)

EnsureLabelsFn = Callable[[str], None]
UpdateIssueFn = Callable[[str, int, str, str], None]
CloseNotPlannedFn = Callable[[str, int], None]


class InvalidInboxKindError(ValueError):
    """種別が`bug` / `enhancement` / `other`以外。"""


class NotInboxIssueError(RuntimeError):
    """対象issueが`inbox`ラベルを持たない（通常issueを誤って編集・削除させない）。"""


def validate_kind(kind: object) -> str:
    if kind not in INBOX_KIND_LABELS:
        raise InvalidInboxKindError(f"不明な種別です: {kind!r}（{', '.join(INBOX_KIND_LABELS)}）")
    return kind  # type: ignore[return-value]


def _validate_title(title: object) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("titleは必須です")
    return title.strip()


def apply_kind_label(
    repo: str,
    issue_number: int,
    kind: str,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
) -> None:
    """種別ラベルをちょうど`kind`の1つにする。現在のラベルを取得し差分のみ適用（冪等）。"""
    current = get_labels(repo, issue_number)
    for label in INBOX_KIND_LABELS:
        if label != kind and label in current:
            remove_label(repo, issue_number, label)
    if kind not in current:
        add_label(repo, issue_number, kind)


def handle_create_inbox(
    repo: str,
    title: str,
    body: str,
    kind: str,
    *,
    create_issue: CreateIssueFn,
    ensure_labels: EnsureLabelsFn,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
) -> int:
    """inbox項目を作成する（`inbox`＋種別ラベル。状態ラベルは付けずディスパッチもしない）。"""
    kind = validate_kind(kind)
    title = _validate_title(title)
    # 対象リポジトリにラベルが無い場合は、未作成ラベルへの付与失敗を避けるため先に作成する。
    ensure_labels(repo)
    issue_number = create_issue(repo, title, body or "")
    add_label(repo, issue_number, INBOX_LABEL)
    apply_kind_label(
        repo,
        issue_number,
        kind,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
    )
    return issue_number


def _require_inbox(repo: str, issue_number: int, get_labels: GetLabelsFn) -> None:
    if INBOX_LABEL not in get_labels(repo, issue_number):
        raise NotInboxIssueError(f"{repo}#{issue_number} はinbox項目ではありません")


def handle_update_inbox(
    repo: str,
    issue_number: int,
    title: str,
    body: str,
    kind: str,
    *,
    update_issue: UpdateIssueFn,
    ensure_labels: EnsureLabelsFn,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
) -> None:
    """inbox項目のタイトル・本文・種別を更新する。種別変更時は旧種別ラベルを外す。"""
    kind = validate_kind(kind)
    title = _validate_title(title)
    _require_inbox(repo, issue_number, get_labels)
    ensure_labels(repo)
    update_issue(repo, issue_number, title, body or "")
    apply_kind_label(
        repo,
        issue_number,
        kind,
        get_labels=get_labels,
        add_label=add_label,
        remove_label=remove_label,
    )


def handle_delete_inbox(
    repo: str,
    issue_number: int,
    *,
    close_not_planned: CloseNotPlannedFn,
    get_labels: GetLabelsFn,
) -> None:
    """inbox項目を`not planned`でクローズする。"""
    _require_inbox(repo, issue_number, get_labels)
    close_not_planned(repo, issue_number)
