"""issueのマイルストーン・ラベルの一括変更（issue #305）。

状態ラベル（`STATUS_LABELS`）は変更対象外とし、要求に含まれていれば拒否する。
マイルストーン・ラベルはリポジトリ上に存在するものだけを選択でき、作成はしない。
issueごとに実行し、部分失敗を許容する。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from orchestrator.labels import STATUS_LABELS, GetLabelsFn

# 1リクエストで変更できるissue数の上限。
MAX_META_ISSUES = 100

MILESTONE_KEEP = "keep"
MILESTONE_SET = "set"
MILESTONE_CLEAR = "clear"


class InvalidMetaRequestError(ValueError):
    """要求が不正（400）。"""


@dataclass(frozen=True)
class MetaRequest:
    issues: list[int]
    milestone_mode: str
    milestone: str | None
    add_labels: list[str]
    remove_labels: list[str]


def _str_list(value: object, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise InvalidMetaRequestError(f"{name}は文字列の配列で指定してください")
    return list(dict.fromkeys(value))


def parse_meta_request(payload: dict) -> MetaRequest:
    issues = payload.get("issues")
    if (
        not isinstance(issues, list)
        or not issues
        or not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in issues)
    ):
        raise InvalidMetaRequestError("issuesは1件以上のissue番号の配列で指定してください")
    issues = list(dict.fromkeys(issues))
    if len(issues) > MAX_META_ISSUES:
        raise InvalidMetaRequestError(f"一度に変更できるissueは{MAX_META_ISSUES}件までです")

    milestone = payload.get("milestone") or {"mode": MILESTONE_KEEP}
    if not isinstance(milestone, dict):
        raise InvalidMetaRequestError("milestoneはオブジェクトで指定してください")
    mode = milestone.get("mode", MILESTONE_KEEP)
    value = milestone.get("value")
    if mode not in (MILESTONE_KEEP, MILESTONE_SET, MILESTONE_CLEAR):
        raise InvalidMetaRequestError("milestone.modeはkeep/set/clearのいずれかです")
    if mode == MILESTONE_SET and (not isinstance(value, str) or not value):
        raise InvalidMetaRequestError("milestone.valueにマイルストーン名を指定してください")

    add = _str_list(payload.get("add_labels"), "add_labels")
    remove = _str_list(payload.get("remove_labels"), "remove_labels")
    protected = sorted((set(add) | set(remove)) & STATUS_LABELS)
    if protected:
        raise InvalidMetaRequestError(f"状態ラベルは変更できません: {', '.join(protected)}")
    both = sorted(set(add) & set(remove))
    if both:
        raise InvalidMetaRequestError(
            f"同じラベルを追加と削除の両方に指定できません: {', '.join(both)}"
        )
    if mode == MILESTONE_KEEP and not add and not remove:
        raise InvalidMetaRequestError("変更内容がありません")
    return MetaRequest(issues, mode, value if mode == MILESTONE_SET else None, add, remove)


def validate_choices(
    request: MetaRequest, *, repo_labels: list[str], open_milestones: list[str]
) -> None:
    """存在しないラベル・マイルストーンを拒否する（作成はしない）。"""
    unknown = sorted((set(request.add_labels) | set(request.remove_labels)) - set(repo_labels))
    if unknown:
        raise InvalidMetaRequestError(f"存在しないラベルです: {', '.join(unknown)}")
    if request.milestone_mode == MILESTONE_SET and request.milestone not in open_milestones:
        raise InvalidMetaRequestError(
            f"存在しない（またはクローズ済みの）マイルストーンです: {request.milestone}"
        )


def apply_meta(
    repo: str,
    request: MetaRequest,
    *,
    get_labels: GetLabelsFn,
    update_issue_meta: Callable[..., None],
) -> dict:
    """issueごとに更新する。現在のラベルとの差分のみ適用し（冪等）、部分失敗を集計する。"""
    succeeded: list[int] = []
    failed: list[dict] = []
    for number in request.issues:
        try:
            current = get_labels(repo, number)
            update_issue_meta(
                repo,
                number,
                milestone=request.milestone,
                clear_milestone=request.milestone_mode == MILESTONE_CLEAR,
                add_labels=[x for x in request.add_labels if x not in current],
                remove_labels=[x for x in request.remove_labels if x in current],
            )
            succeeded.append(number)
        except subprocess.CalledProcessError as e:
            failed.append({"number": number, "error": f"ghコマンドが失敗しました: {e}"})
    return {"succeeded": succeeded, "failed": failed}
