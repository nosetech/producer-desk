"""直接GitHub issue上にコメントされた指示をポーリングで検知するフロー。

仕様: docs/basic-design.md 2-3「共通仕様」
「直接GitHub issue上にコメントされた指示（ダッシュボード経由でない指示）は、
次回ポーリング（最大5分後）でオーケストレータが検知し、同様にディスパッチする。」

起動時点で既にissueに付いているコメントは「既知」として扱い、再処理しない
（起動前の履歴をリプレイしないため）。起動後に新たに増えたコメントのみを
指示として扱い、ラベル遷移・ディスパッチを行う。

オーケストレータ自身が投稿したコメント（`github_client.BOT_COMMENT_MARKER` 付き。
Agent Runnerの実行結果報告、承認/却下/自由記述の定型コメント等）は指示として
扱わない。人間・bot問わず同一のissueコメントとしてポーリングに現れるため、
マーカーが無い場合は自分自身の投稿を新規指示と誤検知し、無限に再ディスパッチ
し続ける（issue #33）。
"""

from __future__ import annotations

from orchestrator.aggregation import IssueSummary
from orchestrator.dispatch_queue import DispatchQueue
from orchestrator.github_client import BOT_COMMENT_MARKER
from orchestrator.instruct import apply_instruction
from orchestrator.labels import AddLabelFn, GetLabelsFn, RemoveLabelFn


class CommentTracker:
    """issueごとに既知のコメントID集合を記録し、新規コメントのみを検知する。"""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, int], set[str]] = {}

    def new_comments(self, repo: str, issue_number: int, comments: list[dict]) -> list[dict]:
        key = (repo, issue_number)
        current_ids = {comment["id"] for comment in comments}

        if key not in self._seen:
            self._seen[key] = current_ids
            return []

        new_comments = [c for c in comments if c["id"] not in self._seen[key]]
        self._seen[key] = current_ids
        return new_comments


def process_new_comments(
    issues_by_repo: dict[str, list[IssueSummary]],
    tracker: CommentTracker,
    *,
    get_labels: GetLabelsFn,
    add_label: AddLabelFn,
    remove_label: RemoveLabelFn,
    dispatch_queue: DispatchQueue,
) -> None:
    for repo, issues in issues_by_repo.items():
        for issue in issues:
            new_comments = tracker.new_comments(repo, issue.number, issue.comments)
            human_comments = [c for c in new_comments if BOT_COMMENT_MARKER not in c["body"]]
            if not human_comments:
                continue

            latest = human_comments[-1]
            apply_instruction(
                repo,
                issue.number,
                latest["body"],
                get_labels=get_labels,
                add_label=add_label,
                remove_label=remove_label,
                dispatch_queue=dispatch_queue,
            )
