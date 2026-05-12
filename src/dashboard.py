"""Dashboard 维护：

- 用 docs/items.json 存最近 N 天的所有采集结果（独立于 dedup state）
- 每次跑都重新渲染 docs/index.html，把 items 嵌入 JSON 直传到前端
- docs/ 目录会被 workflow commit 回仓库，GitHub Pages 自动发布

跟 dedup 的区别：
- dedup state 决定「这条要不要再推送一次到微信」
- dashboard history 决定「网页上显示哪些条目」
两者用同一个 fingerprint 但生命周期不同。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import Item

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
ITEMS_JSON = DOCS_DIR / "items.json"
INDEX_HTML = DOCS_DIR / "index.html"
TEMPLATE_HTML = Path(__file__).resolve().parent / "templates" / "dashboard.html"

HISTORY_DAYS = 7
MAX_ITEMS = 300


class HistoryStore:
    def __init__(self, path: Path = ITEMS_JSON) -> None:
        self.path = path
        self._items: list[dict] = []
        self._fps: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("items.json 解析失败，重置")
            return
        items = data.get("items", []) if isinstance(data, dict) else data
        for it in items:
            fp = it.get("fingerprint")
            if fp and fp not in self._fps:
                self._items.append(it)
                self._fps.add(fp)

    def add(self, items: Iterable[Item]) -> int:
        n = 0
        for it in items:
            fp = it.fingerprint
            if fp in self._fps:
                continue
            self._items.append(it.to_dict())
            self._fps.add(fp)
            n += 1
        return n

    def prune(self, days: int = HISTORY_DAYS, max_items: int = MAX_ITEMS) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept: list[dict] = []
        for it in self._items:
            try:
                ts = datetime.fromisoformat(it.get("fetched_at", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= cutoff:
                kept.append(it)
        kept.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)
        if len(kept) > max_items:
            kept = kept[:max_items]
        self._items = kept
        self._fps = {it["fingerprint"] for it in kept if it.get("fingerprint")}

    def save(self) -> None:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._items),
            "items": self._items,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("dashboard items saved: %d -> %s", len(self._items), self.path)

    @property
    def items(self) -> list[dict]:
        return self._items


def _repo_url() -> str:
    """从 GitHub Actions 环境推断仓库 URL，本地跑时回退到占位。"""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        return f"https://github.com/{repo}"
    return "https://github.com/"


def render_html(history: HistoryStore, output_path: Path = INDEX_HTML) -> None:
    template = TEMPLATE_HTML.read_text(encoding="utf-8")
    data_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": history.items,
    }
    data_json = json.dumps(data_payload, ensure_ascii=False)
    data_json = data_json.replace("</script>", "<\\/script>")

    html = template.replace("__DATA_JSON__", data_json)
    html = html.replace("__REPO_URL__", _repo_url())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info("dashboard html rendered: %s", output_path)


def update(raw_items: list[Item]) -> None:
    """主流程在 dedup 前调用：所有采集结果都进 dashboard。"""
    store = HistoryStore()
    added = store.add(raw_items)
    store.prune()
    store.save()
    render_html(store)
    log.info("dashboard updated: +%d items, total %d", added, len(store.items))
