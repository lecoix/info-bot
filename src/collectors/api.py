"""JSON API 采集器：通过 *_field 配置把任意 JSON 响应映射到 Item。"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx

from ..config import SourceConfig
from ..models import Item

log = logging.getLogger(__name__)


def _pick(obj: Any, path: str) -> str:
    """支持点号路径取值，如 'data.title' 或单层 'title'。"""
    if not path:
        return ""
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return ""
        if cur is None:
            return ""
    return str(cur).strip()


def collect(src: SourceConfig) -> Iterable[Item]:
    log.info("API fetch: %s (%s)", src.name, src.url)
    title_f = src.extra.get("title_field", "title")
    url_f = src.extra.get("url_field", "url")
    summary_f = src.extra.get("summary_field", "")
    items_path = src.extra.get("items_path", "")

    try:
        resp = httpx.get(
            src.url,
            headers={"User-Agent": "info-bot/1.0", "Accept": "application/json"},
            timeout=20.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("API fetch failed %s: %s", src.name, e)
        return []

    if items_path:
        for part in items_path.split("."):
            data = data.get(part) if isinstance(data, dict) else None
            if data is None:
                return []

    if not isinstance(data, list):
        log.warning("API response is not a list for %s", src.name)
        return []

    results: list[Item] = []
    for raw in data[: src.max_items]:
        title = _pick(raw, title_f)
        url = _pick(raw, url_f)
        if not title or not url:
            continue
        summary = _pick(raw, summary_f) if summary_f else ""
        results.append(
            Item(source=src.name, title=title, url=url, summary=summary)
        )
    return results
