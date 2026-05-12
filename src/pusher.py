"""WxPusher 推送封装。

API 文档: https://wxpusher.zjiecode.com/docs/

策略:
- 把多条 Item 按 category 分组聚合成一条 HTML 「晨报」消息推送
- 单条消息过大时（item 太多）才会分批
- 失败重试 2 次
"""
from __future__ import annotations

import html
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx

from .config import AppConfig
from .models import Item

log = logging.getLogger(__name__)

API_URL = "https://wxpusher.zjiecode.com/api/send/message"
# WxPusher 单条标题上限 100，正文 40000。我们留余量。
TITLE_MAX = 80
BODY_MAX = 30000
# 单条消息最多带几条 Item（超过会分批推送，正常一天的量不会触发）
ITEMS_PER_MESSAGE = 40

# 分类元数据：显示名、emoji、推送排序权重
CATEGORY_META: "OrderedDict[str, dict]" = OrderedDict(
    [
        ("rate", {"label": "今日汇率", "icon": "💱", "color": "#f0ad4e"}),
        ("tech", {"label": "科技要闻", "icon": "💻", "color": "#4a90e2"}),
        ("politics", {"label": "时事政治", "icon": "🌐", "color": "#9b59b6"}),
        ("other", {"label": "其他", "icon": "📰", "color": "#888"}),
    ]
)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _bj_today() -> str:
    """北京时间今天的日期字符串，用于晨报标题。"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %A")


def _group_by_category(items: list[Item]) -> "OrderedDict[str, list[Item]]":
    bucket: "OrderedDict[str, list[Item]]" = OrderedDict()
    for cat in CATEGORY_META:
        bucket[cat] = []
    for it in items:
        cat = it.category if it.category in CATEGORY_META else "other"
        bucket[cat].append(it)
    return OrderedDict((k, v) for k, v in bucket.items() if v)


def _render_item(it: Item, max_summary: int, color: str) -> str:
    title = html.escape(it.title)
    source = html.escape(it.source)
    url = html.escape(it.url, quote=True)
    raw_summary = (it.summary or "").strip()
    if raw_summary.startswith("<"):
        summary_html = raw_summary
    else:
        summary_html = html.escape(_truncate(raw_summary, max_summary))
    summary_block = (
        f'<div style="color:#555;font-size:13px;line-height:1.5;margin-top:4px;">'
        f"{summary_html}</div>"
        if summary_html
        else ""
    )
    return (
        f'<div style="margin:0 0 12px 0;padding:8px 10px;'
        f'border-left:3px solid {color};background:#f7f9fc;border-radius:3px;">'
        f'<div style="font-size:12px;color:#888;">{source}</div>'
        f'<div style="font-weight:bold;margin:4px 0;font-size:14px;">'
        f'<a href="{url}" style="color:#1f6feb;text-decoration:none;">{title}</a></div>'
        f"{summary_block}"
        f"</div>"
    )


def _render_html(grouped: "OrderedDict[str, list[Item]]", max_summary: int) -> str:
    parts: list[str] = []
    parts.append(
        f'<div style="font-size:20px;font-weight:bold;margin-bottom:8px;">'
        f"📨 InfoBot 晨报</div>"
        f'<div style="color:#888;font-size:12px;margin-bottom:14px;">{_bj_today()}</div>'
    )
    total = sum(len(v) for v in grouped.values())
    parts.append(
        f'<div style="color:#888;font-size:12px;margin-bottom:14px;">'
        f"今日共 {total} 条新内容</div>"
    )

    for cat, items in grouped.items():
        meta = CATEGORY_META[cat]
        parts.append(
            f'<div style="font-size:16px;font-weight:bold;margin:16px 0 8px 0;'
            f'padding-bottom:4px;border-bottom:2px solid {meta["color"]};">'
            f'{meta["icon"]} {meta["label"]} '
            f'<span style="color:#888;font-weight:normal;font-size:12px;">'
            f"({len(items)})</span></div>"
        )
        for it in items:
            parts.append(_render_item(it, max_summary, meta["color"]))
    return "".join(parts)


def _chunk(items: list[Item], size: int) -> Iterable[list[Item]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def push(config: AppConfig, items: list[Item]) -> int:
    if not items:
        log.info("no new items, skip push")
        return 0

    if config.dry_run:
        log.warning("DRY_RUN=true，跳过真实推送，将打印内容到日志")
        grouped = _group_by_category(items)
        for cat, batch in grouped.items():
            meta = CATEGORY_META[cat]
            log.info("--- %s %s (%d) ---", meta["icon"], meta["label"], len(batch))
            for it in batch:
                log.info("[DRY] %s | %s", it.source, it.title)
        return len(items)

    if not config.wxpusher_token or not config.wxpusher_uids:
        log.error("WXPUSHER_APP_TOKEN 或 WXPUSHER_UIDS 未配置，无法推送")
        return 0

    sent = 0
    batches = list(_chunk(items, ITEMS_PER_MESSAGE))
    total_batch = len(batches)
    for idx, batch in enumerate(batches, 1):
        grouped = _group_by_category(batch)
        suffix = f"（{idx}/{total_batch}）" if total_batch > 1 else ""
        title = _truncate(
            f"{config.settings.title_prefix} 晨报 {_bj_today()} · "
            f"{len(batch)} 条{suffix}",
            TITLE_MAX,
        )
        body = _truncate(
            _render_html(grouped, config.settings.max_content_length), BODY_MAX
        )
        payload = {
            "appToken": config.wxpusher_token,
            "content": body,
            "summary": title,
            "contentType": 2,  # 2 = HTML
            "uids": config.wxpusher_uids,
        }
        if _post_with_retry(payload):
            sent += len(batch)
        time.sleep(0.5)
    return sent


def _post_with_retry(payload: dict, attempts: int = 3) -> bool:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            resp = httpx.post(API_URL, json=payload, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 1000:
                log.info("push ok: %s", data.get("msg"))
                return True
            log.warning("push rejected: %s", data)
            return False
        except Exception as e:
            last_err = e
            log.warning("push attempt %d failed: %s", i + 1, e)
            time.sleep(2 ** i)
    log.error("push failed after retries: %s", last_err)
    return False
