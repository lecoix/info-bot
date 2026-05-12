"""WxPusher 推送封装。

API 文档: https://wxpusher.zjiecode.com/docs/

策略:
- 把多条 Item 聚合为一条 HTML 消息，减少推送次数（WxPusher 免费版每日 1000 条）
- 单条内容过长时截断
- 失败重试 2 次
"""
from __future__ import annotations

import html
import logging
import time
from typing import Iterable

import httpx

from .config import AppConfig
from .models import Item

log = logging.getLogger(__name__)

API_URL = "https://wxpusher.zjiecode.com/api/send/message"
# WxPusher 单条标题上限 100，正文 40000。我们留余量。
TITLE_MAX = 80
BODY_MAX = 30000
# 每条聚合消息最多带几条 Item
ITEMS_PER_MESSAGE = 8


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _render_html(items: list[Item], max_content_length: int) -> str:
    parts: list[str] = []
    for it in items:
        title = html.escape(it.title)
        source = html.escape(it.source)
        url = html.escape(it.url, quote=True)
        summary = _truncate(it.summary, max_content_length)
        # 摘要可能是 HTML，做基础净化：strip 标签风险太高，这里只转义最外层
        summary_html = html.escape(summary) if summary else ""
        summary_block = (
            f'<div style="color:#555;font-size:13px;">{summary_html}</div>'
            if summary_html
            else ""
        )
        parts.append(
            f'<div style="margin-bottom:14px;padding:8px;'
            f'border-left:3px solid #4a90e2;background:#f7f9fc;">'
            f'<div style="font-size:12px;color:#888;">{source}</div>'
            f'<div style="font-weight:bold;margin:4px 0;">'
            f'<a href="{url}">{title}</a></div>'
            f"{summary_block}"
            f"</div>"
        )
    return "".join(parts)


def _chunk(items: list[Item], size: int) -> Iterable[list[Item]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def push(config: AppConfig, items: list[Item]) -> int:
    """推送一批 items，返回成功送达的条数。"""
    if not items:
        log.info("no new items, skip push")
        return 0

    if config.dry_run:
        log.warning("DRY_RUN=true，跳过真实推送，将打印内容到日志")
        for it in items:
            log.info("[DRY] %s | %s", it.source, it.title)
        return len(items)

    if not config.wxpusher_token or not config.wxpusher_uids:
        log.error("WXPUSHER_APP_TOKEN 或 WXPUSHER_UIDS 未配置，无法推送")
        return 0

    sent = 0
    batches = list(_chunk(items, ITEMS_PER_MESSAGE))
    for idx, batch in enumerate(batches, 1):
        title = _truncate(
            f"{config.settings.title_prefix} 新增 {len(batch)} 条"
            f"（{idx}/{len(batches)}）",
            TITLE_MAX,
        )
        body = _truncate(
            _render_html(batch, config.settings.max_content_length), BODY_MAX
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
