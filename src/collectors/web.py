"""HTML 网页采集器：用 BeautifulSoup + CSS 选择器抓静态网页。

不引入 playwright 以保持依赖轻量；动态站点请优先找 RSS / API。
"""
from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..config import SourceConfig
from ..models import Item

log = logging.getLogger(__name__)


def collect(src: SourceConfig) -> Iterable[Item]:
    log.info("Web fetch: %s (%s)", src.name, src.url)
    item_sel = src.extra.get("item_selector")
    title_sel = src.extra.get("title_selector")
    link_sel = src.extra.get("link_selector", title_sel)
    link_attr = src.extra.get("link_attr", "href")
    summary_sel = src.extra.get("summary_selector")

    if not item_sel or not title_sel:
        log.warning("Web source %s 缺少 item_selector / title_selector", src.name)
        return []

    try:
        resp = httpx.get(
            src.url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; info-bot/1.0; "
                    "+https://github.com/)"
                )
            },
            timeout=20.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning("Web fetch failed %s: %s", src.name, e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results: list[Item] = []
    for node in soup.select(item_sel)[: src.max_items]:
        title_el = node.select_one(title_sel)
        link_el = node.select_one(link_sel) if link_sel else title_el
        if not title_el or not link_el:
            continue
        title = title_el.get_text(strip=True)
        href = link_el.get(link_attr, "")
        if not title or not href:
            continue
        url = urljoin(src.url, href)
        summary = ""
        if summary_sel:
            s_el = node.select_one(summary_sel)
            if s_el:
                summary = s_el.get_text(" ", strip=True)
        results.append(
            Item(source=src.name, title=title, url=url, summary=summary)
        )
    return results
