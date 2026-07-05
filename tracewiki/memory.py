from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import MemoryItem, utc_now_iso
from .retriever import cosine, tokenize
from .wiki_builder import stable_id


MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  memory_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  memory_type TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  support_count INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_user_status
ON memories(user_id, status, updated_at);
"""


class MemoryService:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(MEMORY_SCHEMA)

    def add(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        confidence: float = 0.65,
        source: str = "manual",
        memory_id: str | None = None,
        status: str = "active",
    ) -> MemoryItem:
        metadata = metadata or {}
        memory_id = memory_id or stable_id(f"{user_id}|{memory_type}|{metadata.get('key') or content}")
        existing = self.get(memory_id)
        if existing:
            merged_metadata = merge_metadata(existing.metadata, metadata)
            return self.update(
                memory_id,
                content=content,
                metadata=merged_metadata,
                confidence=max(existing.confidence, clamp_confidence(confidence)),
                source=source,
                status=status,
                support_delta=1,
            ) or existing

        now = utc_now_iso()
        item = MemoryItem(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content.strip(),
            metadata=metadata,
            confidence=clamp_confidence(confidence),
            source=source,
            status=status,
            support_count=1,
            created_at=now,
            updated_at=now,
        )
        self._insert_or_replace(item)
        return item

    def list(
        self,
        user_id: str,
        memory_type: str | None = None,
        status: str | None = "active",
        limit: int = 80,
    ) -> list[MemoryItem]:
        query = """
            SELECT memory_id, user_id, memory_type, content, metadata_json,
                   confidence, source, status, support_count, created_at, updated_at
            FROM memories
            WHERE user_id = ?
        """
        params: list[Any] = [user_id]
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[MemoryItem]:
        query_tokens = tokenize(query)
        query_counter = counter(query_tokens)
        scored: list[tuple[float, MemoryItem]] = []
        for item in self.list(user_id=user_id, memory_type=memory_type, status="active", limit=200):
            searchable = " ".join([item.content, json.dumps(item.metadata, ensure_ascii=False)])
            lexical = cosine(query_counter, counter(tokenize(searchable))) if query_tokens else 0.0
            global_boost = 0.14 if item.memory_type in {"response_preference", "output_format", "task_habit"} else 0.0
            confidence_boost = item.confidence * 0.06
            support_boost = min(item.support_count, 5) * 0.02
            score = lexical + global_boost + confidence_boost + support_boost
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
        return [item for _, item in scored[:limit]]

    def get(self, memory_id: str) -> MemoryItem | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT memory_id, user_id, memory_type, content, metadata_json,
                       confidence, source, status, support_count, created_at, updated_at
                FROM memories
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float | None = None,
        source: str | None = None,
        status: str | None = None,
        support_delta: int = 0,
    ) -> MemoryItem | None:
        item = self.get(memory_id)
        if not item:
            return None
        updated = MemoryItem(
            memory_id=item.memory_id,
            user_id=item.user_id,
            memory_type=item.memory_type,
            content=(content if content is not None else item.content).strip(),
            metadata=metadata if metadata is not None else item.metadata,
            confidence=clamp_confidence(confidence) if confidence is not None else item.confidence,
            source=source or item.source,
            status=status or item.status,
            support_count=max(1, item.support_count + support_delta),
            created_at=item.created_at,
            updated_at=utc_now_iso(),
        )
        self._insert_or_replace(updated)
        return updated

    def delete(self, memory_id: str) -> bool:
        with self._connect() as con:
            cursor = con.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
            return cursor.rowcount > 0

    def extract_and_update(
        self,
        user_id: str,
        question: str,
        answer: str,
        *,
        feedback: str = "",
        action: str = "auto_logged",
        accepted: bool = True,
    ) -> list[MemoryItem]:
        candidates = extract_memory_candidates(question, answer, feedback, action, accepted)
        return [self.add(user_id=user_id, source="rule_extractor", **candidate) for candidate in candidates]

    def _insert_or_replace(self, item: MemoryItem) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO memories
                (memory_id, user_id, memory_type, content, metadata_json,
                 confidence, source, status, support_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id,
                    item.user_id,
                    item.memory_type,
                    item.content,
                    json.dumps(item.metadata, ensure_ascii=False),
                    item.confidence,
                    item.source,
                    item.status,
                    item.support_count,
                    item.created_at,
                    item.updated_at,
                ),
            )

    def _from_row(self, row: tuple[Any, ...]) -> MemoryItem:
        return MemoryItem(
            memory_id=row[0],
            user_id=row[1],
            memory_type=row[2],
            content=row[3],
            metadata=json.loads(row[4]),
            confidence=float(row[5]),
            source=row[6],
            status=row[7],
            support_count=int(row[8]),
            created_at=row[9],
            updated_at=row[10],
        )


def extract_memory_candidates(
    question: str,
    answer: str,
    feedback: str = "",
    action: str = "auto_logged",
    accepted: bool = True,
) -> list[dict[str, Any]]:
    del answer
    text = "\n".join([question, feedback, action]).lower()
    signal = {"question": question[:240], "feedback": feedback[:240], "action": action, "accepted": accepted}
    candidates: list[dict[str, Any]] = []

    if has_any(text, ["短一点", "简短", "直接", "先给结论", "make_shorter"]):
        candidates.append(candidate("length:conclusion_first", "response_preference", "用户偏好简洁回答，先给结论，避免长篇背景铺垫。", 0.82, signal))
    if has_any(text, ["详细", "展开", "讲清楚", "完整", "make_more_detailed"]):
        candidates.append(candidate("length:detailed_when_needed", "response_preference", "复杂问题需要结构化展开，补齐关键步骤。", 0.78, signal))
    if has_any(text, ["表格", "对比", "add_table"]):
        candidates.append(candidate("format:table_for_comparison", "output_format", "复杂对比或方案权衡时，用户偏好使用表格。", 0.86, signal))
    if has_any(text, ["代码", "实现", "落地", "模块", "工程", "add_code"]):
        candidates.append(candidate("habit:engineering_first", "task_habit", "技术问题优先给工程落地路径，必要时补充代码或接口形态。", 0.82, signal))
    if has_any(text, ["步骤", "一步步", "流程", "add_steps"]):
        candidates.append(candidate("format:steps", "output_format", "复杂任务应拆成可执行步骤。", 0.8, signal))
    if has_any(text, ["ppt", "展示", "答辩", "make_ppt"]):
        candidates.append(candidate("format:presentation_ready", "output_format", "面向展示或答辩时，用户偏好 PPT 友好的结构和表达。", 0.78, signal))
    if not accepted or has_any(text, ["not_helpful", "没帮助", "不对", "错误", "不准确"]):
        candidates.append(candidate("feedback:evidence_next_step", "response_preference", "证据不足时要明确说明，并给出可执行下一步。", 0.76, signal))

    return dedupe(candidates)


def memory_prompt(memories: list[MemoryItem]) -> str:
    if not memories:
        return "无长期记忆命中。"
    lines = ["以下长期记忆只能用于调整表达方式、输出结构和任务习惯，不能当作事实证据："]
    for item in memories:
        lines.append(f"- [{item.memory_type} confidence={item.confidence:.2f} support={item.support_count}] {item.content}")
    return "\n".join(lines)


def candidate(key: str, memory_type: str, content: str, confidence: float, signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_type": memory_type,
        "content": content,
        "metadata": {"key": key, "signals": [signal]},
        "confidence": confidence,
    }


def has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def counter(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def clamp_confidence(value: float) -> float:
    return max(0.0, min(0.99, float(value)))


def merge_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing, **incoming}
    merged["signals"] = [
        item
        for item in list(existing.get("signals", [])) + list(incoming.get("signals", []))
        if isinstance(item, dict)
    ][-6:]
    merged["last_observed_at"] = utc_now_iso()
    return merged


def dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in candidates:
        key = item["metadata"]["key"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
