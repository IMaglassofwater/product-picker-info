"""Best-effort WxPusher notifications for the production daily runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import os
import sys
from hashlib import sha256
from typing import Callable

import requests


WXPUSHER_API_URL = "https://wxpusher.zjiecode.com/api/send/message"
REPORT_URL = "https://65sk9kjfnxz3dzan43yso4.streamlit.app/"
DEFAULT_TIMEOUT_SECONDS = 12
ACCEPTANCE_DELIVERY_CHANNEL = "wxpusher_full_fidelity_acceptance"


@dataclass(frozen=True)
class NotificationTopPick:
    title: str
    score: int
    reason: str


@dataclass(frozen=True)
class DailyNotificationSummary:
    status: str
    new_products: int = 0
    ai_analyzed: int = 0
    qualified: int = 0
    top_picks: list[NotificationTopPick] = field(default_factory=list)
    failed_sources: list[tuple[str, str]] = field(default_factory=list)
    failed_stage: str = ""
    error: str = ""
    run_url: str = ""


class WxPusherNotifier:
    """Send one bounded WxPusher request without exposing credentials."""

    def __init__(
        self,
        app_token: str,
        uid: str,
        *,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        post: Callable[..., requests.Response] = requests.post,
        warning: Callable[[str], None] = print,
    ) -> None:
        self.app_token = app_token.strip()
        self.uid = uid.strip()
        self.timeout = timeout
        self._post = post
        self._warning = warning

    @classmethod
    def from_env(cls, **kwargs) -> "WxPusherNotifier":
        return cls(
            os.getenv("WXPUSHER_APP_TOKEN", ""),
            os.getenv("WXPUSHER_UID", ""),
            **kwargs,
        )

    @property
    def configured(self) -> bool:
        return bool(self.app_token and self.uid)

    def send(self, title: str, html_content: str, *, url: str = REPORT_URL) -> bool:
        if not self.configured:
            self._warning("WARNING: WxPusher notification skipped (credentials missing)")
            return False
        payload = {
            "appToken": self.app_token,
            "content": html_content,
            "summary": title[:100],
            "contentType": 2,
            "uids": [self.uid],
            "url": url,
        }
        try:
            response = self._post(WXPUSHER_API_URL, json=payload, timeout=self.timeout)
            if not 200 <= response.status_code < 300:
                self._warning(
                    f"WARNING: WxPusher notification failed (HTTP {response.status_code})"
                )
                return False
            data = response.json()
            if not isinstance(data, dict) or data.get("code") != 1000:
                self._warning("WARNING: WxPusher notification failed (invalid API response)")
                return False
            return True
        except requests.Timeout:
            self._warning("WARNING: WxPusher notification failed (timeout)")
        except (requests.RequestException, ValueError, TypeError) as exc:
            self._warning(
                f"WARNING: WxPusher notification failed ({type(exc).__name__})"
            )
        return False


def _clean(value: object, limit: int = 240) -> str:
    return escape(" ".join(str(value or "").split())[:limit])


def render_daily_message(summary: DailyNotificationSummary) -> tuple[str, str]:
    """Render a compact Chinese HTML message from already-computed pipeline facts."""
    if summary.status == "FAILED":
        title = "Product Picker 今日运行失败 ❌"
        parts = [
            f"<h3>{title}</h3>",
            f"<p><b>失败阶段：</b>{_clean(summary.failed_stage or 'Daily Pipeline')}</p>",
            f"<p><b>错误：</b>{_clean(summary.error or '未知错误')}</p>",
        ]
        if summary.run_url:
            parts.append(f'<p><a href="{escape(summary.run_url, quote=True)}">查看 GitHub Actions</a></p>')
        return title, "".join(parts)

    partial = bool(summary.failed_sources) or summary.status == "PARTIAL"
    title = (
        "Product Picker 今日选品完成（部分数据源异常）⚠️"
        if partial else "Product Picker 今日选品完成 ✅"
    )
    parts = [
        f"<h3>{title}</h3>",
        "<ul>",
        f"<li>今日新增产品：{summary.new_products}</li>",
        f"<li>今日 AI 分析：{summary.ai_analyzed}</li>",
        f"<li>Qualified：{summary.qualified}</li>",
        f"<li>Top Picks：{len(summary.top_picks)}</li>",
        "</ul>",
    ]
    if summary.top_picks:
        parts.append("<h4>今日 Top 3</h4><ol>")
        for item in summary.top_picks[:3]:
            parts.append(
                f"<li><b>{_clean(item.title, 80)}</b>（{item.score}分）<br>"
                f"{_clean(item.reason, 180)}</li>"
            )
        parts.append("</ol>")
    if summary.failed_sources:
        parts.append("<h4>异常数据源</h4><ul>")
        for source, error in summary.failed_sources:
            parts.append(f"<li>{_clean(source, 60)}：{_clean(error, 160)}</li>")
        parts.append("</ul>")
    parts.append(f'<p><a href="{REPORT_URL}">打开完整报告</a></p>')
    return title, "".join(parts)


def send_daily_notification(
    summary: DailyNotificationSummary,
    *,
    notifier: WxPusherNotifier | None = None,
) -> bool:
    sender = notifier or WxPusherNotifier.from_env()
    title, content = render_daily_message(summary)
    return sender.send(title, content, url=summary.run_url or REPORT_URL)


def send_connectivity_test(*, notifier: WxPusherNotifier | None = None) -> bool:
    sender = notifier or WxPusherNotifier.from_env()
    return sender.send(
        "Product Picker 微信通知测试",
        "<p>Product Picker 微信自动通知连接正常 ✅</p>",
    )


def notification_delivery_key(daily_run_id: str, uid: str, channel: str = "wxpusher") -> tuple[str, str]:
    """Return non-secret stable delivery and recipient identities."""
    recipient_hash = sha256(uid.encode("utf-8")).hexdigest()
    key = sha256(f"{daily_run_id}|{channel}|{recipient_hash}".encode("utf-8")).hexdigest()
    return key, recipient_hash


def send_full_fidelity_daily(
    dataset: dict, *, notifier: WxPusherNotifier | None = None,
    is_delivered: Callable[[str], bool] = lambda _key: False,
    record_delivery: Callable[[str, str, str, int, int], None] = lambda *_args: None,
    max_chars: int = 39000,
) -> bool:
    """Fail closed on persistence/parity and mark complete only after every chunk."""
    from daily_direction_report import render_wxpusher_messages, validate_web_wxpusher_parity

    sender = notifier or WxPusherNotifier.from_env()
    run_id = str(dataset.get("run_id") or dataset.get("daily_discovery_run_id") or "")
    if not run_id or not dataset.get("items") or not sender.configured:
        return False
    try:
        messages = render_wxpusher_messages(dataset, max_chars=max_chars)
    except ValueError as exc:
        sender._warning(f"WARNING: WxPusher full-fidelity report not sent ({exc})")
        return False
    parity = validate_web_wxpusher_parity(dataset, messages)
    if not parity["overall"]:
        return False
    delivery_key, recipient_hash = notification_delivery_key(run_id, sender.uid)
    if is_delivered(delivery_key):
        return True
    delivered = 0
    record_delivery(delivery_key, run_id, recipient_hash, len(messages), delivered)
    for message in messages:
        if not sender.send(f"今日产品发现 {message['message_index']}/{message['total_messages']}", message["content"]):
            record_delivery(delivery_key, run_id, recipient_hash, len(messages), delivered)
            return False
        delivered += 1
        record_delivery(delivery_key, run_id, recipient_hash, len(messages), delivered)
    return delivered == len(messages)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args != ["--test"]:
        print("Usage: python -m wxpusher_notifier --test")
        return 2
    return 0 if send_connectivity_test() else 1


if __name__ == "__main__":
    raise SystemExit(main())
