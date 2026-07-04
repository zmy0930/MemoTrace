from __future__ import annotations

import re


ALIASES = {
    "向量数据库": "vector-database",
    "向量库": "vector-database",
    "向量检索": "vector-search",
    "知识图谱": "knowledge-graph",
    "大语言模型": "llm",
    "large language model": "llm",
    "large-language-model": "llm",
    "wiki links": "wikilink",
    "wiki-links": "wikilink",
    "wikilinks": "wikilink",
    "embeddings": "embedding",
    "vector embeddings": "embedding",
}


def normalize_concept(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    if lowered in ALIASES:
        return ALIASES[lowered]
    if text in ALIASES:
        return ALIASES[text]
    slug = re.sub(r"[\s_]+", "-", lowered)
    slug = re.sub(r"[^a-z0-9+\-\u4e00-\u9fff]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or lowered
