"""汇率采集器。

默认走 https://api.frankfurter.app （欧洲央行参考汇率，免费、无 key、
工作日更新；周末和节假日返回最后一个工作日的值）。

配置示例（sources.yaml）:

    - name: 澳元兑人民币
      type: rate
      url: https://api.frankfurter.app/latest
      base: AUD
      target: CNY
      category: rate

也支持显示对比基准（如想看 USD/CNY 同时显示前一日变化），暂未实现。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx

from ..config import SourceConfig
from ..models import Item

log = logging.getLogger(__name__)


def _fetch(url: str, params: dict) -> dict | None:
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"User-Agent": "info-bot/1.0"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("rate fetch failed: %s", e)
        return None


def collect(src: SourceConfig) -> Iterable[Item]:
    base = (src.extra.get("base") or "AUD").upper()
    target = (src.extra.get("target") or "CNY").upper()
    log.info("Rate fetch: %s (%s -> %s)", src.name, base, target)

    today = _fetch(src.url, {"from": base, "to": target})
    if not today:
        return []

    rate = (today.get("rates") or {}).get(target)
    date_str = today.get("date", "")
    if rate is None or not date_str:
        log.warning("rate response missing fields: %s", today)
        return []

    yesterday_rate = _previous_rate(src.url, base, target, date_str)
    delta_html, delta_text = _format_delta(rate, yesterday_rate)

    title = f"1 {base} = {rate:.4f} {target} {delta_text}".strip()
    summary = (
        f'<div>参考日期: <b>{date_str}</b></div>'
        f'<div style="font-size:24px;margin:6px 0;">'
        f"<b>1 {base} = {rate:.4f} {target}</b>{delta_html}"
        f"</div>"
        f'<div style="color:#888;font-size:12px;">数据源: 欧洲央行 (frankfurter.app)</div>'
    )
    item_url = f"https://www.frankfurter.app/{date_str}?from={base}&to={target}"

    return [
        Item(
            source=src.name,
            title=title,
            url=item_url,
            summary=summary,
        )
    ]


def _previous_rate(api_url: str, base: str, target: str, today_iso: str) -> float | None:
    """frankfurter 没有 'previous day' 接口，手动往前找最近的工作日。"""
    try:
        cur = datetime.fromisoformat(today_iso).date()
    except ValueError:
        return None
    for back in range(1, 8):
        d = (cur - timedelta(days=back)).isoformat()
        endpoint = api_url.rstrip("/").rsplit("/", 1)[0] + f"/{d}"
        data = _fetch(endpoint, {"from": base, "to": target})
        if data and data.get("date") and data.get("rates", {}).get(target):
            return data["rates"][target]
    return None


def _format_delta(today_rate: float, yesterday_rate: float | None) -> tuple[str, str]:
    if yesterday_rate is None or yesterday_rate == 0:
        return "", ""
    diff = today_rate - yesterday_rate
    pct = diff / yesterday_rate * 100
    if abs(diff) < 1e-6:
        sym, color, arrow = "持平", "#888", "→"
    elif diff > 0:
        sym, color, arrow = "升值", "#d9534f", "↑"
    else:
        sym, color, arrow = "贬值", "#5cb85c", "↓"
    html_part = (
        f' <span style="color:{color};font-size:14px;">'
        f"{arrow} {diff:+.4f} ({pct:+.2f}%) {sym}</span>"
    )
    text_part = f"{arrow}{pct:+.2f}%"
    return html_part, text_part
