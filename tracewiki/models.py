from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceRecord:
    source_id: str
    path: str
    filename: str
    modality: str
    mime_type: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class KnowledgeCard:
    card_id: str
    title: str
    summary: str
    tags: list[str]
    category: str
    source_id: str
    source_path: str
    content: str
    evidence: list[dict[str, Any]]
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def filename(self) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.title).strip("_")
        return f"{safe or self.card_id}.md"


@dataclass
class SearchResult:
    card_id: str
    title: str
    snippet: str
    score: float
    source_path: str
    evidence: list[dict[str, Any]]
    span_id: str = ""
    locator: str = ""


@dataclass
class Claim:
    text: str
    evidence: list[dict[str, Any]]
    confidence: float


@dataclass
class Answer:
    text: str
    claims: list[Claim]
    used_results: list[SearchResult]


@dataclass
class QASession:
    session_id: str
    question: str
    answer: str
    evidence: list[dict[str, Any]]
    graph_mermaid: str
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class InteractionLog:
    log_id: str
    question: str
    answer_summary: str
    answer_type: str
    user_feedback: str
    user_action: str
    accepted: bool
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class PreferenceCandidate:
    candidate_id: str
    field: str
    old_value: str
    new_value: str
    evidence: str
    confidence: float
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class SourceSpan:
    span_id: str
    source_id: str
    card_id: str
    source_path: str
    locator: str
    text: str
    span_type: str
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class SystemLog:
    log_id: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class VectorRecord:
    item_id: str
    item_type: str
    text: str
    vector: list[float]
    metadata: dict[str, Any]
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class StagingItem:
    staging_id: str
    title: str
    url: str
    summary: str
    content: str
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class WikiMaintenanceProposal:
    proposal_id: str
    proposal_type: str
    title: str
    rationale: str
    proposed_content: str
    target_card_id: str = ""
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)
