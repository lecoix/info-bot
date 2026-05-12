"""统一数据模型。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Item:
    """单条采集到的信息。所有采集器的输出都收敛到这个结构。"""

    source: str
    title: str
    url: str
    summary: str = ""
    category: str = "other"
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def fingerprint(self) -> str:
        """用于去重的稳定指纹。优先 URL，否则降级到标题+源。"""
        key = self.url.strip() if self.url else f"{self.source}::{self.title}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "category": self.category,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat(),
            "fingerprint": self.fingerprint,
        }
