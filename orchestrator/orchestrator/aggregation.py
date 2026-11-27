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
from typing import Protocol

from orchestrator.dispatch_queue import QueueSnapshot
from orchestrator.labels import (
    INBOX_KIND_BUG,
    INBOX_KIND_ENHANCEMENT,
    INBOX_KIND_OTHER,
    INBOX_LABEL,
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_LABEL_PRIORITY,
    STATUS_LABELS,
    STATUS_NEEDS_HUMAN_DECISION,
    STATUS_TODO,
)
from orchestrator.limit_wait import LimitWait, extract_limit_wait_marker

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

# `DispatchQueue.snapshot(repo)` と同じシグネチャの関数型（issue #233）。
GetQueueSnapshotFn = Callable[[str], QueueSnapshot]


class PlanJobLike(Protocol):
    """キュー表示に必要な計画ジョブの属性（`plan_jobs.PlanJob`、issue #335）。"""

    id: str
    request: str
    inbox_issue_number: int | None
    result: dict | None


# キュー上の計画ジョブ番号（負数）から計画ジョブを引く関数型（issue #335）。
# キュー待ち中に破棄された（`PlanJobStore`に無い）ジョブはNoneを返す。
ResolvePlanJobFn = Callable[[int], PlanJobLike | None]


@dataclass
class PrCandidate:
    """issueの対応PR候補（issue #206）。ダッシュボードのPR選択UIに表示する。"""

    number: int
    title: str
    url: str
    is_draft: bool = False
    head_ref_name: str = ""
    base_ref_name: str = ""


@dataclass
class IssueSummary:
    repo: str
    number: int
    title: str
    labels: list[str]
    comments: list[dict]
    updated_at: str
    state: str = "OPEN"
    # `status:in-review`・`needs-human-decision` のissueについてのみ、
    # ポーリング時に紐づくPR番号を解決して埋める
    # （orchestrator.polling.poll_once参照、issue #58, #270）。
    pr_number: int | None = None
    # `pr_number`が一意に特定できなかった（候補が0件または2件以上）場合も含め、
    # 対応PRの候補一覧（issue #206）。承認時はこの候補からユーザーが選択する。
    pr_candidates: list[PrCandidate] = field(default_factory=list)
    # inbox項目（issue #288）の表示用。`gh issue list`が返すissue本文・作成日時（ISO 8601）。
    body: str = ""
    created_at: str = ""
    # マイルストーンのタイトル（issue #303）。未設定ならNone。
    milestone: str | None = None
    # 利用リミット待ちで自動再開が予定されている判断待ちissueのみ（issue #331）。
    # `aggregate()`が判断待ち一覧を作る際に最新コメントのマーカーから埋める。
    limit_wait: LimitWaitInfo | None = None


@dataclass
class LimitWaitInfo:
    """ダッシュボード表示用の利用リミット待ち情報（issue #331）。"""

    # 解除予定時刻（ISO 8601、タイムゾーン付き）。この時刻を過ぎた後のポーリングで自動再開する。
    reset_at: str
    # 連続の自動再開のうち何回目の待機か（1始まり）。
    attempt: int


@dataclass
class InboxItem:
    """inbox項目（`inbox`ラベル付きissue、issue #288）の1件。"""

    number: int
    title: str
    # `bug` / `enhancement` / `other`。種別ラベルが0個・複数の場合は`other`扱い。
    kind: str
    body: str
    created_at: str


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
    # オーケストレータが実際にGitHubからこのリポジトリのissueを取得した時刻（ISO 8601, UTC）。
    # ダッシュボードの「N分前に更新」表示の元（issue #197）。未取得ならNone。
    fetched_at: str | None = None
    # このリポジトリのOPENなinbox項目（登録日時の新しい順、issue #288）。
    inbox: list[InboxItem] = field(default_factory=list)


@dataclass
class QueueEntry:
    """ディスパッチキュー上の1エントリ（issue #233）。表示用のissue情報を付与する。"""

    number: int
    # issueがissues_by_repoに無い（クローズ済み・取得失敗）場合はNone（番号のみ表示する）。
    title: str | None = None
    # 5つの状態ラベルのうち表示に採用する1つ。issueが無い・状態ラベル未付与の場合はNone。
    label: str | None = None
    # エントリの種別（issue #335）。"issue"（自走タスク）または"plan"（AI計画ジョブ）。
    # 計画ジョブの`number`は負の内部番号のため、表示には使わない。`title`には依頼文の1行目
    # （ジョブが解決できない場合はNone）、`label`は常にNoneを入れる。
    kind: str = "issue"
    plan_job_id: str | None = None
    # inbox由来の計画ジョブなら元のinbox項目のissue番号。新規タスク由来・自走タスクはNone。
    inbox_issue_number: int | None = None
    # 計画ジョブが既に計画（直前の結果）を持つ＝修正指示の実行・待機中か。ダッシュボードは
    # inbox由来でこれが真のときだけ、ピン留めしたツールチップに「計画を開く」を出す。
    plan_revising: bool = False


@dataclass
class ProjectQueue:
    """プロジェクトのディスパッチキュー状態（issue #233）。"""

    running: QueueEntry | None = None
    waiting: list[QueueEntry] = field(default_factory=list)


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
    # オーケストレータの最終ポーリング時刻（全プロジェクト一括取得の完了時刻、ISO 8601, UTC。
    # issue #197）。未ポーリングならNone。
    last_polled_at: str | None = None
    # 集約の元になったリポジトリ別issue一覧。プロジェクト単位の再取得（issue #197）で
    # 当該リポジトリ分のみ差し替えて再集約するためStateStoreが保持する内部用データで、
    # APIレスポンスには含めない（server._handle_state参照）。
    issues_by_repo: dict[str, list[IssueSummary]] = field(default_factory=dict)


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


_INBOX_KINDS = (INBOX_KIND_BUG, INBOX_KIND_ENHANCEMENT, INBOX_KIND_OTHER)


def is_inbox_issue(issue: IssueSummary) -> bool:
    """`inbox`ラベルを持ち、状態ラベル（5種）が未付与のissueか（issue #288）。

    昇格すると`inbox`ラベルが外れて`status:todo`が付与されるため、状態ラベルが付いた
    issueは（`inbox`が残っていても）通常のissueとして扱う。
    """
    return INBOX_LABEL in issue.labels and not any(label in STATUS_LABELS for label in issue.labels)


def inbox_kind(labels: list[str]) -> str:
    """種別ラベルからinbox項目の種別を導出する。ちょうど1つでなければ`other`。"""
    present = [label for label in labels if label in _INBOX_KINDS]
    return present[0] if len(present) == 1 else INBOX_KIND_OTHER


def build_inbox(issues: list[IssueSummary]) -> list[InboxItem]:
    """1リポジトリのOPENなinbox項目を、登録日時の新しい順で返す。"""
    items = [
        InboxItem(
            number=i.number,
            title=i.title,
            kind=inbox_kind(i.labels),
            body=i.body,
            created_at=i.created_at,
        )
        for i in issues
        if i.state == "OPEN" and is_inbox_issue(i)
    ]
    items.sort(key=lambda i: (i.created_at, i.number), reverse=True)
    return items


def latest_ci_wait_pr_number(issue: IssueSummary) -> int | None:
    """issueの最新コメントがCI待機マーカー付きのAgent Runner投稿であれば対象PR番号を返す。

    最新コメントのみを見る。CI待機後に別の（マーカーの無い）コメントが追加されて
    いれば、そのCI待機は既に解消済み（後続処理が進んだ、または人間が介入した）と
    みなせるため。
    """
    # agent_runner / github_client は本モジュールをimportするため、循環回避で遅延import
    from orchestrator.agent_runner import extract_ci_wait_marker
    from orchestrator.github_client import BOT_COMMENT_MARKER

    if not issue.comments:
        return None
    body = issue.comments[-1].get("body", "")
    if BOT_COMMENT_MARKER not in body:
        return None
    return extract_ci_wait_marker(body)


def latest_limit_wait(issue: IssueSummary) -> LimitWait | None:
    """最新コメントが利用リミット待ちマーカー付きのBot投稿ならその内容を返す（issue #331）。

    最新コメントのみを見る。マーカーの後に人間の返信・別モデル指定・取り消しコメントが
    付いていれば、自動再開は予定されていないとみなす。
    """
    from orchestrator.github_client import BOT_COMMENT_MARKER

    if not issue.comments:
        return None
    body = issue.comments[-1].get("body", "")
    if BOT_COMMENT_MARKER not in body:
        return None
    return extract_limit_wait_marker(body)


def _is_orphaned_in_progress(
    issue: IssueSummary, label: str, is_dispatch_active: IsDispatchActiveFn | None
) -> bool:
    """`status:in-progress`のissueなのにディスパッチキュー上で動いていないかを判定する。

    最新コメントがCI待機マーカー付きの場合は、Agent Runnerが意図的にターンを終えて
    オーケストレータのポーリングによる再開を待つ正常状態のため孤立とみなさない
    （issue #314。`ci_watcher.build_in_progress_breakdown`のCI待ちと同じ判定）。

    `is_dispatch_active`が渡されない場合（テスト・呼び出し元がディスパッチ状態を
    持たない場合）は判定不能として常にFalseを返す（誤検知を避ける）。
    """
    if is_dispatch_active is None or label != STATUS_IN_PROGRESS:
        return False
    if is_dispatch_active(issue.repo, issue.number):
        return False
    return latest_ci_wait_pr_number(issue) is None


@dataclass
class ProjectIssue:
    """プロジェクト別issue一覧ページ（issue #116）の1行分。"""

    number: int
    title: str
    # 5つの状態ラベルのうち表示に採用する1つ。クローズ済みで状態ラベルが未付与のissueは
    # `status:closed`として扱い、OPENで状態ラベルが無いissue（タグなし）はNone。
    label: str | None
    state: str
    comments_count: int
    updated_at: str
    # `status:in-progress`なのに対応するAgent Runnerが実行中でない孤立状態か（issue #50）。
    is_orphaned: bool
    # マイルストーンのタイトル（issue #303）。未設定ならNone。
    milestone: str | None = None
    # 状態ラベル5種を除いたその他のラベル名（issue #303）。
    tags: list[str] = field(default_factory=list)


def build_project_issues(
    issues: list[IssueSummary],
    is_dispatch_active: IsDispatchActiveFn | None = None,
) -> list[ProjectIssue]:
    """1リポジトリのissue一覧を、issue一覧ページ向けに状態ラベル・孤立判定付きで整形する。"""
    result: list[ProjectIssue] = []
    for issue in issues:
        if is_inbox_issue(issue):
            continue  # inboxは専用セクションで表示する（issue #288）
        label = _current_status_label(issue)
        if label is None and issue.state == "CLOSED":
            label = STATUS_CLOSED
        result.append(
            ProjectIssue(
                number=issue.number,
                title=issue.title,
                label=label,
                state=issue.state,
                comments_count=len(issue.comments),
                updated_at=issue.updated_at,
                is_orphaned=label is not None
                and _is_orphaned_in_progress(issue, label, is_dispatch_active),
                milestone=issue.milestone,
                tags=[name for name in issue.labels if name not in STATUS_LABELS],
            )
        )
    result.sort(key=lambda i: i.updated_at, reverse=True)
    return result


def aggregate(
    issues_by_repo: dict[str, list[IssueSummary]],
    is_dispatch_active: IsDispatchActiveFn | None = None,
    *,
    fetched_at_by_repo: dict[str, str] | None = None,
    last_polled_at: str | None = None,
) -> AggregatedState:
    """リポジトリ別のissue一覧を、判断待ち一覧・レビュー待ち一覧・プロジェクト状況に集約する。

    `fetched_at_by_repo`・`last_polled_at`（issue #197）を渡すと、プロジェクト状況の
    `fetched_at`・集約結果の`last_polled_at`に反映する。

    `is_dispatch_active`（`DispatchQueue.is_active`、issue #50）を渡すと、プロジェクト
    状況の各要素に孤立したin-progressの検知結果（`ProjectStatus.is_orphaned`）を含める。
    """
    all_issues = [issue for issues in issues_by_repo.values() for issue in issues]

    decisions = [issue for issue in all_issues if STATUS_NEEDS_HUMAN_DECISION in issue.labels]
    decisions.sort(key=lambda issue: issue.updated_at, reverse=True)
    for issue in decisions:
        wait = latest_limit_wait(issue)
        issue.limit_wait = (
            LimitWaitInfo(reset_at=wait.reset_at.isoformat(), attempt=wait.attempt)
            if wait is not None
            else None
        )

    reviews = [issue for issue in all_issues if STATUS_IN_REVIEW in issue.labels]
    reviews.sort(key=lambda issue: issue.updated_at, reverse=True)

    status_counts = dict.fromkeys(STATUS_COUNT_KEYS, 0)
    project_status: list[ProjectStatus] = []

    fetched_at_by_repo = fetched_at_by_repo or {}
    for repo, issues in issues_by_repo.items():
        fetched_at = fetched_at_by_repo.get(repo)
        inbox = build_inbox(issues)
        labeled: list[tuple[IssueSummary, str]] = []
        repo_counts = dict.fromkeys(STATUS_COUNT_KEYS, 0)

        for issue in issues:
            if is_inbox_issue(issue):
                continue  # inboxは状態別件数・並行状況の集計に含めない（issue #288）
            label = _current_status_label(issue)
            if label is not None:
                labeled.append((issue, label))
            if issue.state == "OPEN":
                count_key = label or STATUS_COUNT_UNTAGGED
                if count_key in repo_counts:
                    repo_counts[count_key] += 1
                    status_counts[count_key] += 1

        if not labeled:
            project_status.append(
                ProjectStatus(repo=repo, counts=repo_counts, fetched_at=fetched_at, inbox=inbox)
            )
            continue

        latest_issue, latest_label = max(labeled, key=lambda pair: pair[0].updated_at)
        project_status.append(
            ProjectStatus(
                repo=repo,
                label=latest_label,
                number=latest_issue.number,
                title=latest_issue.title,
                # 理由不明の孤立issueが1件でもあればTrue（`in_progress_breakdown.orphaned > 0`
                # と一致させる。直近更新の1件だけでは判定しない、issue #314）
                is_orphaned=any(
                    _is_orphaned_in_progress(issue, label, is_dispatch_active)
                    for issue, label in labeled
                    if issue.state == "OPEN"
                ),
                counts=repo_counts,
                fetched_at=fetched_at,
                inbox=inbox,
            )
        )

    return AggregatedState(
        decisions=decisions,
        reviews=reviews,
        project_status=project_status,
        status_counts=status_counts,
        last_polled_at=last_polled_at,
        issues_by_repo=issues_by_repo,
    )


def build_project_queue(
    snapshot: QueueSnapshot,
    issues: list[IssueSummary],
    resolve_plan: ResolvePlanJobFn | None = None,
) -> ProjectQueue:
    """キューのスナップショットに、issue番号で引いたタイトル・状態ラベルを付与する（#233）。

    計画ジョブ（負の番号、issue #335）は`resolve_plan`で引いた依頼文を持つ`kind="plan"`の
    エントリにする。キュー待ち中に破棄された（解決できない）計画ジョブは実行されずに
    捨てられるため待機列から除く。実行中のものは空き枠にならないよう種別だけのエントリにする。
    """
    by_number = {issue.number: issue for issue in issues}

    def plan_entry(number: int) -> QueueEntry | None:
        job = resolve_plan(number) if resolve_plan is not None else None
        if job is None:
            return None
        lines = job.request.strip().splitlines()
        return QueueEntry(
            number=number,
            title=lines[0].strip() if lines else None,
            kind="plan",
            plan_job_id=job.id,
            inbox_issue_number=job.inbox_issue_number,
            plan_revising=job.result is not None,
        )

    def entry(number: int) -> QueueEntry | None:
        if number < 0:
            return plan_entry(number)
        issue = by_number.get(number)
        if issue is None:
            return QueueEntry(number=number)
        return QueueEntry(number=number, title=issue.title, label=_current_status_label(issue))

    running: QueueEntry | None = None
    if snapshot.running is not None:
        running = entry(snapshot.running) or QueueEntry(number=snapshot.running, kind="plan")
    waiting = [e for e in (entry(n) for n in snapshot.waiting) if e is not None]
    return ProjectQueue(running=running, waiting=waiting)
