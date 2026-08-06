"""orchestrator.slack_notifier の単体テスト。

docs/basic-design.md 5-2のメッセージフォーマット、および判断待ちの新規発生検知
（起動時点で既存の判断待ちは通知しない）を、フェイクのwebhook送信関数で検証する。
"""

from __future__ import annotations

from orchestrator.aggregation import ActivityEvent, AggregatedState, IssueSummary
from orchestrator.slack_notifier import (
    DecisionNotifier,
    ReviewNotifier,
    format_decision_message,
    format_review_message,
)


class FakeWebhook:
    def __init__(self) -> None:
        self.posted: list[tuple[str, dict]] = []

    def __call__(self, webhook_url: str, payload: dict) -> None:
        self.posted.append((webhook_url, payload))


def _issue(
    repo: str = "nosetech/project-a", number: int = 12, title: str = "ログイン機能について"
) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title=title,
        labels=["needs-human-decision"],
        comments=[],
        updated_at="2026-08-01T00:00:00Z",
    )


def test_format_decision_message_matches_basic_design_template() -> None:
    message = format_decision_message(_issue())

    assert message == (
        ":bell: 判断待ちが発生しました\n"
        "*リポジトリ*: nosetech/project-a\n"
        "*issue*: #12 ログイン機能について\n"
        "https://github.com/nosetech/project-a/issues/12"
    )


def test_first_poll_seeds_known_decisions_without_notifying() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )

    notifier.notify_new_decisions(AggregatedState(decisions=[_issue()], activity=[]))

    assert webhook.posted == []


def test_newly_appearing_decision_is_notified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))

    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[issue], activity=[]))

    assert len(webhook.posted) == 1
    assert webhook.posted[0][0] == "https://hooks.example/x"
    assert webhook.posted[0][1] == {"text": format_decision_message(issue)}


def test_unchanged_decision_is_not_renotified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))
    notifier.notify_new_decisions(AggregatedState(decisions=[issue], activity=[]))

    notifier.notify_new_decisions(AggregatedState(decisions=[issue], activity=[]))

    assert len(webhook.posted) == 1


def test_decision_that_disappears_and_reappears_is_renotified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))
    notifier.notify_new_decisions(AggregatedState(decisions=[issue], activity=[]))
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))

    notifier.notify_new_decisions(AggregatedState(decisions=[issue], activity=[]))

    assert len(webhook.posted) == 2


def test_missing_webhook_url_skips_notification_but_still_tracks_state() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(post_webhook=webhook, get_webhook_url=lambda: None)
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))

    notifier.notify_new_decisions(AggregatedState(decisions=[_issue()], activity=[]))

    assert webhook.posted == []


def test_multiple_new_decisions_in_one_poll_are_each_notified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_decisions(AggregatedState(decisions=[], activity=[]))

    issue_a = _issue(number=1)
    issue_b = _issue(number=2)
    notifier.notify_new_decisions(AggregatedState(decisions=[issue_a, issue_b], activity=[]))

    assert len(webhook.posted) == 2


def _review_event(
    repo: str = "nosetech/project-a", number: int = 38, title: str = "ブラウザエラーの調査・対応"
) -> ActivityEvent:
    return ActivityEvent(
        repo=repo,
        number=number,
        title=title,
        label="status:in-review",
        updated_at="2026-08-06T00:00:00Z",
    )


def test_format_review_message_matches_basic_design_template() -> None:
    message = format_review_message(_review_event())

    assert message == (
        ":mag: レビュー待ちになりました\n"
        "*リポジトリ*: nosetech/project-a\n"
        "*issue*: #38 ブラウザエラーの調査・対応\n"
        "https://github.com/nosetech/project-a/issues/38"
    )


def test_first_poll_seeds_known_reviews_without_notifying() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )

    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[_review_event()]))

    assert webhook.posted == []


def test_newly_appearing_review_is_notified() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[]))

    event = _review_event()
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[event]))

    assert len(webhook.posted) == 1
    assert webhook.posted[0][0] == "https://hooks.example/x"
    assert webhook.posted[0][1] == {"text": format_review_message(event)}


def test_unchanged_review_is_not_renotified() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    event = _review_event()
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[]))
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[event]))

    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[event]))

    assert len(webhook.posted) == 1


def test_non_review_activity_is_ignored() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[]))

    in_progress_event = ActivityEvent(
        repo="nosetech/project-a",
        number=1,
        title="実装中のタスク",
        label="status:in-progress",
        updated_at="2026-08-06T00:00:00Z",
    )
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[in_progress_event]))

    assert webhook.posted == []


def test_missing_webhook_url_skips_review_notification_but_still_tracks_state() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(post_webhook=webhook, get_webhook_url=lambda: None)
    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[]))

    notifier.notify_new_reviews(AggregatedState(decisions=[], activity=[_review_event()]))

    assert webhook.posted == []
