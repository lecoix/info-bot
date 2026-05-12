"""基于 state/seen.json 的去重。

存储结构：
{
    "<fingerprint>": {"first_seen": "ISO-8601", "title": "...", "source": "..."}
}

为防止状态文件无限增长，超过 max_entries 时按 first_seen 截断保留最新部分。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Item

log = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"
MAX_ENTRIES = 5000


class SeenStore:
    def __init__(self, path: Path = DEFAULT_STATE_PATH) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("seen.json 解析失败，重置")
                self._data = {}
        else:
            self._data = {}

    def filter_new(self, items: Iterable[Item]) -> list[Item]:
        return [it for it in items if it.fingerprint not in self._data]

    def mark_seen(self, items: Iterable[Item]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for it in items:
            self._data.setdefault(
                it.fingerprint,
                {"first_seen": now, "title": it.title, "source": it.source},
            )

    def save(self) -> None:
        if len(self._data) > MAX_ENTRIES:
            ordered = sorted(
                self._data.items(),
                key=lambda kv: kv[1].get("first_seen", ""),
                reverse=True,
            )
            self._data = dict(ordered[:MAX_ENTRIES])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        log.info("state saved: %d entries -> %s", len(self._data), self.path)
