"""判断待ち（needs-human-decision）・レビュー待ち（status:in-review）
新規発生時のSlack通知。

仕様: docs/basic-design.md 5-1・5-2、docs/architecture.md 6章

起動時点で既に判断待ち・レビュー待ちのissueは「既知」として扱い通知しない
（オーケストレータ再起動のたびに既存の判断待ち・レビュー待ちを再通知しないため。
comment_watcher.CommentTrackerと同様の方針）。以降のポーリングで新規に
判断待ち・レビュー待ちになったissueのみを通知対象とする。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from collections.abc import Callable

from orchestrator.aggregation import AggregatedState, IssueSummary
from orchestrator.plan_jobs import STATUS_FAILED, STATUS_SUCCEEDED, PlanJob

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL_ENV = "SLACK_WEBHOOK_URL"

PostWebhookFn = Callable[[str, dict], None]
GetWebhookUrlFn = Callable[[], str | None]


def format_decision_message(issue: IssueSummary) -> str:
    url = f"https://github.com/{issue.repo}/issues/{issue.number}"
    return (
        f":bell: 判断待ちが発生しました\n"
        f"*リポジトリ*: {issue.repo}\n"
        f"*issue*: #{issue.number} {issue.title}\n"
        f"{url}"
    )


def post_slack_webhook(webhook_url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        response.read()


def _default_get_webhook_url() -> str | None:
    return os.environ.get(SLACK_WEBHOOK_URL_ENV)


class DecisionNotifier:
    """判断待ちissueの新規発生を検知し、Slackに通知する。"""

    def __init__(
        self,
        *,
        post_webhook: PostWebhookFn = post_slack_webhook,
        get_webhook_url: GetWebhookUrlFn = _default_get_webhook_url,
    ) -> None:
        self._post_webhook = post_webhook
        self._get_webhook_url = get_webhook_url
        self._known: set[tuple[str, int]] | None = None

    def notify_new_decisions(self, state: AggregatedState) -> None:
        current = {(issue.repo, issue.number) for issue in state.decisions}

        if self._known is None:
            self._known = current
            return

        new_keys = current - self._known
        self._known = current

        if not new_keys:
            return

        webhook_url = self._get_webhook_url()
        if not webhook_url:
            return

        for issue in state.decisions:
            if (issue.repo, issue.number) in new_keys:
                self._post_webhook(webhook_url, {"text": format_decision_message(issue)})


def format_review_message(issue: IssueSummary) -> str:
    url = f"https://github.com/{issue.repo}/issues/{issue.number}"
    return (
        f":mag: レビュー待ちになりました\n"
        f"*リポジトリ*: {issue.repo}\n"
        f"*issue*: #{issue.number} {issue.title}\n"
        f"{url}"
    )


class ReviewNotifier:
    """レビュー待ち（status:in-review）issueの新規発生を検知し、Slackに通知する。"""

    def __init__(
        self,
        *,
        post_webhook: PostWebhookFn = post_slack_webhook,
        get_webhook_url: GetWebhookUrlFn = _default_get_webhook_url,
    ) -> None:
        self._post_webhook = post_webhook
        self._get_webhook_url = get_webhook_url
        self._known: set[tuple[str, int]] | None = None

    def notify_new_reviews(self, state: AggregatedState) -> None:
        current = {(issue.repo, issue.number) for issue in state.reviews}

        if self._known is None:
            self._known = current
            return

        new_keys = current - self._known
        self._known = current

        if not new_keys:
            return

        webhook_url = self._get_webhook_url()
        if not webhook_url:
            return

        for issue in state.reviews:
            if (issue.repo, issue.number) in new_keys:
                self._post_webhook(webhook_url, {"text": format_review_message(issue)})


DASHBOARD_URL_ENV = "DASHBOARD_URL"
PLAN_REQUEST_SUMMARY_LENGTH = 80
PLAN_FAILURE_LABELS = {
    "parse": "出力を解釈できませんでした",
    "timeout": "タイムアウト",
    "limit": "利用リミット到達",
    "interrupted": "再起動により中断",
    "failed": "失敗",
}


def _summarize(text: str) -> str:
    one_line = " ".join(text.split())
    if len(one_line) > PLAN_REQUEST_SUMMARY_LENGTH:
        return one_line[:PLAN_REQUEST_SUMMARY_LENGTH] + "…"
    return one_line


def format_plan_message(job: PlanJob) -> str:
    """AI計画ジョブの完了・失敗通知（issue #299）。プロジェクト・依頼要約・結果・導線を含む。"""
    target = f"（inbox #{job.inbox_issue_number}）" if job.inbox_issue_number else "（新規タスク）"
    if job.status == STATUS_SUCCEEDED:
        head = ":white_check_mark: AI計画が完成しました（確認待ち）"
        result = "成功"
    else:
        code = (job.error or {}).get("code", "failed")
        head = ":warning: AI計画の作成に失敗しました"
        result = f"失敗（{code}: {PLAN_FAILURE_LABELS.get(code, '失敗')}）"
    lines = [
        head,
        f"*プロジェクト*: {job.repo}{target}",
        f"*依頼内容*: {_summarize(job.request)}",
        f"*結果*: {result}",
    ]
    dashboard_url = os.environ.get(DASHBOARD_URL_ENV)
    if dashboard_url:
        lines.append(dashboard_url)
    else:
        lines.append("ダッシュボードのissue一覧（inbox）で確認してください")
    return "\n".join(lines)


class PlanNotifier:
    """計画ジョブが`succeeded`/`failed`になった時点でSlackに通知する（issue #299）。

    `PlanRunner`が1ジョブの完了ごとに1回だけ`notify`を呼ぶため重複通知は起きない。
    送信失敗は計画の結果に影響させずログ警告に留める。
    """

    def __init__(
        self,
        *,
        post_webhook: PostWebhookFn = post_slack_webhook,
        get_webhook_url: GetWebhookUrlFn = _default_get_webhook_url,
    ) -> None:
        self._post_webhook = post_webhook
        self._get_webhook_url = get_webhook_url

    def notify(self, job: PlanJob) -> None:
        if job.status not in (STATUS_SUCCEEDED, STATUS_FAILED):
            return
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            return
        try:
            self._post_webhook(webhook_url, {"text": format_plan_message(job)})
        except Exception:  # noqa: BLE001
            logger.warning("計画ジョブのSlack通知に失敗しました: %s", job.id, exc_info=True)
