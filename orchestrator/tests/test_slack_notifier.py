"""orchestrator.slack_notifier の単体テスト。

docs/basic-design.md 5-2のメッセージフォーマット、および判断待ちの新規発生検知
（起動時点で既存の判断待ちは通知しない）を、フェイクのwebhook送信関数で検証する。
"""

from __future__ import annotations

from orchestrator.aggregation import AggregatedState, IssueSummary
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

    notifier.notify_new_decisions(AggregatedState(decisions=[_issue()]))

    assert webhook.posted == []


def test_newly_appearing_decision_is_notified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_decisions(AggregatedState(decisions=[]))

    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[issue]))

    assert len(webhook.posted) == 1
    assert webhook.posted[0][0] == "https://hooks.example/x"
    assert webhook.posted[0][1] == {"text": format_decision_message(issue)}


def test_unchanged_decision_is_not_renotified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[]))
    notifier.notify_new_decisions(AggregatedState(decisions=[issue]))

    notifier.notify_new_decisions(AggregatedState(decisions=[issue]))

    assert len(webhook.posted) == 1


def test_decision_that_disappears_and_reappears_is_renotified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    issue = _issue()
    notifier.notify_new_decisions(AggregatedState(decisions=[]))
    notifier.notify_new_decisions(AggregatedState(decisions=[issue]))
    notifier.notify_new_decisions(AggregatedState(decisions=[]))

    notifier.notify_new_decisions(AggregatedState(decisions=[issue]))

    assert len(webhook.posted) == 2


def test_missing_webhook_url_skips_notification_but_still_tracks_state() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(post_webhook=webhook, get_webhook_url=lambda: None)
    notifier.notify_new_decisions(AggregatedState(decisions=[]))

    notifier.notify_new_decisions(AggregatedState(decisions=[_issue()]))

    assert webhook.posted == []


def test_multiple_new_decisions_in_one_poll_are_each_notified() -> None:
    webhook = FakeWebhook()
    notifier = DecisionNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_decisions(AggregatedState(decisions=[]))

    issue_a = _issue(number=1)
    issue_b = _issue(number=2)
    notifier.notify_new_decisions(AggregatedState(decisions=[issue_a, issue_b]))

    assert len(webhook.posted) == 2


def _review_issue(
    repo: str = "nosetech/project-a", number: int = 38, title: str = "ブラウザエラーの調査・対応"
) -> IssueSummary:
    return IssueSummary(
        repo=repo,
        number=number,
        title=title,
        labels=["status:in-review"],
        comments=[],
        updated_at="2026-08-06T00:00:00Z",
    )


def test_format_review_message_matches_basic_design_template() -> None:
    message = format_review_message(_review_issue())

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

    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[_review_issue()]))

    assert webhook.posted == []


def test_newly_appearing_review_is_notified() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[]))

    issue = _review_issue()
    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[issue]))

    assert len(webhook.posted) == 1
    assert webhook.posted[0][0] == "https://hooks.example/x"
    assert webhook.posted[0][1] == {"text": format_review_message(issue)}


def test_unchanged_review_is_not_renotified() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(
        post_webhook=webhook, get_webhook_url=lambda: "https://hooks.example/x"
    )
    issue = _review_issue()
    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[]))
    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[issue]))

    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[issue]))

    assert len(webhook.posted) == 1


def test_missing_webhook_url_skips_review_notification_but_still_tracks_state() -> None:
    webhook = FakeWebhook()
    notifier = ReviewNotifier(post_webhook=webhook, get_webhook_url=lambda: None)
    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[]))

    notifier.notify_new_reviews(AggregatedState(decisions=[], reviews=[_review_issue()]))

    assert webhook.posted == []


# issue #299: AI計画ジョブの完了・失敗通知。
def _plan_job(status: str, **kwargs):
    from orchestrator.plan_jobs import PlanJob

    return PlanJob(
        id="a1",
        repo="o/r",
        request="ログイン画面を直したい\n詳細あり",
        model=None,
        inbox_issue_number=kwargs.pop("inbox_issue_number", None),
        status=status,
        created_at="t",
        updated_at="t",
        **kwargs,
    )


def test_plan_notifier_posts_success_and_failure_with_kind() -> None:
    from orchestrator.slack_notifier import PlanNotifier

    posted: list[dict] = []
    notifier = PlanNotifier(
        post_webhook=lambda url, payload: posted.append(payload), get_webhook_url=lambda: "u"
    )

    notifier.notify(_plan_job("succeeded", inbox_issue_number=5))
    notifier.notify(_plan_job("failed", error={"code": "timeout", "message": "m"}))
    notifier.notify(_plan_job("running"))

    assert len(posted) == 2
    assert "完成" in posted[0]["text"] and "inbox #5" in posted[0]["text"]
    assert "o/r" in posted[0]["text"] and "ログイン画面を直したい 詳細あり" in posted[0]["text"]
    assert "失敗" in posted[1]["text"] and "timeout" in posted[1]["text"]


def test_plan_notifier_skips_without_webhook_and_swallows_send_errors() -> None:
    from orchestrator.slack_notifier import PlanNotifier

    PlanNotifier(
        post_webhook=lambda *a: (_ for _ in ()).throw(AssertionError("呼ばれない")),
        get_webhook_url=lambda: None,
    ).notify(_plan_job("succeeded"))

    def boom(url, payload):
        raise OSError("down")

    PlanNotifier(post_webhook=boom, get_webhook_url=lambda: "u").notify(_plan_job("succeeded"))
