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
import os
import urllib.request
from collections.abc import Callable

from orchestrator.aggregation import ActivityEvent, AggregatedState, IssueSummary
from orchestrator.labels import STATUS_IN_REVIEW

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


def format_review_message(event: ActivityEvent) -> str:
    url = f"https://github.com/{event.repo}/issues/{event.number}"
    return (
        f":mag: レビュー待ちになりました\n"
        f"*リポジトリ*: {event.repo}\n"
        f"*issue*: #{event.number} {event.title}\n"
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
        reviews = [event for event in state.activity if event.label == STATUS_IN_REVIEW]
        current = {(event.repo, event.number) for event in reviews}

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

        for event in reviews:
            if (event.repo, event.number) in new_keys:
                self._post_webhook(webhook_url, {"text": format_review_message(event)})
