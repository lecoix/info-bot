"""RSS / Atom 采集器。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser

from ..config import SourceConfig
from ..models import Item

log = logging.getLogger(__name__)


def _to_datetime(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def collect(src: SourceConfig) -> Iterable[Item]:
    log.info("RSS fetch: %s (%s)", src.name, src.url)
    feed = feedparser.parse(src.url, request_headers={"User-Agent": "info-bot/1.0"})
    if feed.bozo and not feed.entries:
        log.warning("RSS parse warning %s: %s", src.name, feed.bozo_exception)
        return []

    items: list[Item] = []
    for entry in feed.entries[: src.max_items]:
        title = (getattr(entry, "title", "") or "").strip()
        url = (getattr(entry, "link", "") or "").strip()
        if not title or not url:
            continue
        summary = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        ).strip()
        published_at = _to_datetime(
            getattr(entry, "published_parsed", None)
            or getattr(entry, "updated_parsed", None)
        )
        items.append(
            Item(
                source=src.name,
                title=title,
                url=url,
                summary=summary,
                published_at=published_at,
            )
        )
    return items
