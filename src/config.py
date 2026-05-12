"""配置加载：从 sources.yaml 和环境变量读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SourceConfig:
    name: str
    type: str
    url: str
    enabled: bool = True
    max_items: int = 10
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalSettings:
    max_push_per_run: int = 20
    max_content_length: int = 800
    enable_summary: bool = False
    title_prefix: str = "[InfoBot]"


@dataclass
class AppConfig:
    sources: list[SourceConfig]
    settings: GlobalSettings
    wxpusher_token: str
    wxpusher_uids: list[str]
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    dry_run: bool = False


_KNOWN_KEYS = {"name", "type", "url", "enabled", "max_items"}


def _load_dotenv(path: Path) -> None:
    """轻量级 .env 加载，避免引入额外依赖。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def load_config(root: Path | None = None) -> AppConfig:
    root = root or Path(__file__).resolve().parent.parent
    _load_dotenv(root / ".env")

    yaml_path = root / "sources.yaml"
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sources: list[SourceConfig] = []
    for raw in data.get("sources", []):
        extra = {k: v for k, v in raw.items() if k not in _KNOWN_KEYS}
        sources.append(
            SourceConfig(
                name=raw["name"],
                type=raw["type"],
                url=raw["url"],
                enabled=raw.get("enabled", True),
                max_items=raw.get("max_items", 10),
                extra=extra,
            )
        )

    s = data.get("settings") or {}
    settings = GlobalSettings(
        max_push_per_run=s.get("max_push_per_run", 20),
        max_content_length=s.get("max_content_length", 800),
        enable_summary=s.get("enable_summary", False),
        title_prefix=s.get("title_prefix", "[InfoBot]"),
    )

    uids_raw = os.environ.get("WXPUSHER_UIDS", "").strip()
    uids = [u.strip() for u in uids_raw.split(",") if u.strip()]

    return AppConfig(
        sources=sources,
        settings=settings,
        wxpusher_token=os.environ.get("WXPUSHER_APP_TOKEN", "").strip(),
        wxpusher_uids=uids,
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").strip(),
        llm_model=os.environ.get("LLM_MODEL", "deepseek-chat").strip(),
        dry_run=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
    )
