from __future__ import annotations

import os
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from tracewiki.config import Settings, load_settings
from tracewiki.memory import MemoryService
from tracewiki.storage import KnowledgeStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    os.environ.setdefault("TRACEWIKI_DATA_DIR", str(PROJECT_ROOT / "data"))
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> KnowledgeStore:
    settings = get_settings()
    return KnowledgeStore(settings.sqlite_path, settings.wiki_dir)


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    return MemoryService(get_settings().sqlite_path)


def settings_with_model_overrides(
    api_key: str | None = None,
    base_url: str | None = None,
    text_model: str | None = None,
    vision_model: str | None = None,
    embedding_model: str | None = None,
) -> Settings:
    settings = get_settings()
    return replace(
        settings,
        openai_api_key=api_key.strip() if api_key and api_key.strip() else settings.openai_api_key,
        openai_base_url=base_url.strip() if base_url and base_url.strip() else settings.openai_base_url,
        text_model=text_model.strip() if text_model and text_model.strip() else settings.text_model,
        vision_model=vision_model.strip() if vision_model and vision_model.strip() else settings.vision_model,
        embedding_model=(
            embedding_model.strip()
            if embedding_model and embedding_model.strip()
            else settings.embedding_model
        ),
    )
