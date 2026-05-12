"""LLM 摘要：调用 OpenAI 兼容的 Chat Completions 接口。

默认走 DeepSeek（便宜、国内可访问、OpenAI 兼容协议）。
只对长度超过阈值的 summary 调用 LLM，避免浪费 token。
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

import httpx

from .config import AppConfig
from .models import Item

log = logging.getLogger(__name__)

MIN_LENGTH_TO_SUMMARIZE = 300
TARGET_LENGTH = 120
PROMPT = (
    "你是新闻摘要助手。请用中文将下面的内容压缩成不超过 {n} 字的一句话概要，"
    "保留关键事实，不要加任何前缀、不要用 markdown：\n\n{content}"
)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")


def summarize_all(config: AppConfig, items: Iterable[Item]) -> None:
    """就地修改每条 Item 的 summary 字段。LLM 不可用时静默跳过。"""
    if not config.settings.enable_summary or not config.llm_api_key:
        return

    client = httpx.Client(
        base_url=config.llm_base_url,
        headers={
            "Authorization": f"Bearer {config.llm_api_key}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    try:
        for it in items:
            plain = _strip_html(it.summary).strip()
            if len(plain) < MIN_LENGTH_TO_SUMMARIZE:
                it.summary = plain
                continue
            try:
                it.summary = _ask(client, config.llm_model, plain)
            except Exception as e:
                log.warning("summarize failed for %s: %s", it.title, e)
                it.summary = plain[:TARGET_LENGTH] + "…"
    finally:
        client.close()


def _ask(client: httpx.Client, model: str, content: str) -> str:
    prompt = PROMPT.format(n=TARGET_LENGTH, content=content[:4000])
    resp = client.post(
        "/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
