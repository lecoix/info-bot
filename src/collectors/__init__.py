"""采集器：把不同来源的内容归一为 Item。"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceConfig
from ..models import Item
from . import api, rate, rss, web

_DISPATCH = {
    "rss": rss.collect,
    "api": api.collect,
    "web": web.collect,
    "rate": rate.collect,
}


def collect_source(src: SourceConfig) -> Iterable[Item]:
    fn = _DISPATCH.get(src.type)
    if fn is None:
        raise ValueError(f"未知信息源类型: {src.type}")
    return fn(src)
