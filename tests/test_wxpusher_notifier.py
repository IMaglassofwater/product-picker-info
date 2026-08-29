"""Unit tests for the isolated WxPusher notification boundary."""

from __future__ import annotations

import requests

import run_daily
from wxpusher_notifier import (
    DailyNotificationSummary,
    NotificationTopPick,
    WxPusherNotifier,
    render_daily_message,
    send_connectivity_test,
)


class Response:
    def __init__(self, status_code=200, data=None, json_error=None):
        self.status_code = status_code
        self.data = {"code": 1000} if data is None else data
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.data


def test_successful_send_uses_uid_html_and_timeout_without_logging_secrets():
    calls, warnings = [], []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    notifier = WxPusherNotifier("secret-token", "UID_123", post=post, warning=warnings.append)
    assert notifier.send("title", "<b>hello</b>") is True
    assert calls[0][1]["timeout"] == 12
    assert calls[0][1]["json"]["uids"] == ["UID_123"]
    assert calls[0][1]["json"]["contentType"] == 2
    assert warnings == []


def test_non_2xx_is_failure_and_warning_has_no_secret():
    warnings = []
    notifier = WxPusherNotifier(
        "secret-token", "UID_123", post=lambda *_args, **_kwargs: Response(503),
        warning=warnings.append,
    )
    assert notifier.send("title", "body") is False
    assert "503" in warnings[0]
    assert "secret-token" not in warnings[0] and "UID_123" not in warnings[0]


def test_timeout_is_bounded_failure():
    attempts = 0

    def timeout(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise requests.Timeout("late")

    assert WxPusherNotifier("token", "uid", post=timeout, warning=lambda _x: None).send(
        "title", "body"
    ) is False
    assert attempts == 1


def test_missing_secret_skips_network():
    assert WxPusherNotifier("", "uid", post=lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("network called")
    ), warning=lambda _x: None).send("title", "body") is False


def test_malformed_response_is_failure():
    notifier = WxPusherNotifier(
        "token", "uid", post=lambda *_a, **_k: Response(data={"unexpected": True}),
        warning=lambda _x: None,
    )
    assert notifier.send("title", "body") is False
    notifier = WxPusherNotifier(
        "token", "uid", post=lambda *_a, **_k: Response(json_error=ValueError("bad")),
        warning=lambda _x: None,
    )
    assert notifier.send("title", "body") is False


def test_partial_message_keeps_summary_and_source_error():
    summary = DailyNotificationSummary(
        "PARTIAL", 4, 2, 3,
        [NotificationTopPick("中文产品", 88, "明确机会")],
        [("Reddit", "HTTP 500")],
    )
    title, body = render_daily_message(summary)
    assert "部分数据源异常" in title
    assert "今日新增产品：4" in body and "Reddit：HTTP 500" in body


def test_failed_message_contains_stage_error_and_actions_link():
    title, body = render_daily_message(DailyNotificationSummary(
        "FAILED", failed_stage="Ranking", error="database unavailable",
        run_url="https://github.com/example/repo/actions/runs/123",
    ))
    assert "今日运行失败" in title
    assert "Ranking" in body and "database unavailable" in body
    assert "actions/runs/123" in body


def test_connectivity_test_sends_only_fixed_message():
    sent = []

    class Sender:
        def send(self, title, content, **_kwargs):
            sent.append((title, content))
            return True

    assert send_connectivity_test(notifier=Sender()) is True
    assert sent == [("Product Picker 微信通知测试", "<p>Product Picker 微信自动通知连接正常 ✅</p>")]


def test_notification_failure_does_not_change_pipeline_exit(monkeypatch):
    result = run_daily.DailyRunResult("run-1", "SUCCESS", 0, "", {
        "new_products": 1, "qualified_count": 0, "top_picks": [],
        "triage": {"successful": 0}, "sources": [],
    })
    monkeypatch.setattr(run_daily, "execute_daily", lambda: result)
    monkeypatch.setattr(
        run_daily, "send_daily_notification",
        lambda _summary: (_ for _ in ()).throw(RuntimeError("notification unavailable")),
    )
    assert run_daily.main() == 0
