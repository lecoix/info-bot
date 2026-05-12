"""主流程：加载配置 → 采集 → 去重 → 摘要 → 推送 → 保存状态。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from . import dashboard
from .collectors import collect_source
from .config import load_config
from .dedup import SeenStore
from .models import Item
from .pusher import push
from .summarizer import summarize_all

log = logging.getLogger("info-bot")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def collect_all(config) -> list[Item]:
    out: list[Item] = []
    for src in config.sources:
        if not src.enabled:
            log.info("skip disabled source: %s", src.name)
            continue
        try:
            items = list(collect_source(src))
            for it in items:
                if it.category == "other":
                    it.category = src.category
            log.info("source %s [%s] -> %d items", src.name, src.category, len(items))
            out.extend(items)
        except Exception as e:
            log.exception("source %s failed: %s", src.name, e)
    return out


def main() -> int:
    setup_logging()
    root = Path(__file__).resolve().parent.parent
    config = load_config(root)
    log.info(
        "loaded %d sources, dry_run=%s, enable_summary=%s",
        len(config.sources),
        config.dry_run,
        config.settings.enable_summary,
    )

    raw_items = collect_all(config)
    log.info("collected %d items total", len(raw_items))

    # Dashboard 比 dedup 宽松：所有采集结果都进历史，独立于推送状态
    try:
        dashboard.update(raw_items)
    except Exception as e:
        log.exception("dashboard update failed: %s", e)

    store = SeenStore()
    new_items = store.filter_new(raw_items)
    log.info("after dedup: %d new items", len(new_items))

    cap = config.settings.max_push_per_run
    if len(new_items) > cap:
        log.warning("trim %d -> %d to respect max_push_per_run", len(new_items), cap)
        new_items = new_items[:cap]

    if not new_items:
        log.info("nothing new, exit")
        return 0

    summarize_all(config, new_items)
    sent = push(config, new_items)
    log.info("pushed %d items", sent)

    if sent > 0:
        store.mark_seen(new_items)
        store.save()
    else:
        log.warning("nothing successfully pushed, state not updated")

    return 0


if __name__ == "__main__":
    sys.exit(main())
