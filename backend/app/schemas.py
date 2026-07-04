from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SourceInfo(BaseModel):
    source_id: str
    path: str
    filename: str
    modality: str
    mime_type: str
    created_at: str


class CardInfo(BaseModel):
    card_id: str
    title: str
    summary: str
    tags: list[str]
    category: str
    source_id: str
    source_path: str
    content: str
    evidence: list[dict[str, Any]]
    created_at: str


class WikiPageInfo(BaseModel):
    filename: str
    content: str


class GraphNodeInfo(BaseModel):
    id: str
    label: str
    type: str
    data: dict[str, Any]


class GraphEdgeInfo(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    weight: float
    data: dict[str, Any]


class GraphCommunityInfo(BaseModel):
    id: str
    label: str
    card_ids: list[str]
    card_titles: list[str]
    size: int
    span_count: int
    tags: list[str]


class KnowledgeGraphInfo(BaseModel):
    nodes: list[GraphNodeInfo]
    edges: list[GraphEdgeInfo]
    communities: list[GraphCommunityInfo]
    stats: dict[str, int]


class WikiProposalInfo(BaseModel):
    proposal_id: str
    proposal_type: str
    title: str
    rationale: str
    proposed_content: str
    target_card_id: str
    status: str
    created_at: str


class UploadResponse(BaseModel):
    card: CardInfo
    message: str


class BatchUploadResponse(BaseModel):
    cards: list[CardInfo]
    message: str


class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class EvidenceResult(BaseModel):
    title: str
    score: float
    locator: str
    source: str
    snippet: str


class AskResponse(BaseModel):
    answer: str
    claims: list[dict[str, Any]]
    graph_mermaid: str
    evidence: list[EvidenceResult]


class QASessionInfo(BaseModel):
    session_id: str
    question: str
    answer: str
    evidence: list[dict[str, Any]]
    graph_mermaid: str
    created_at: str


class HealthIssueInfo(BaseModel):
    title: str
    severity: str
    issue_type: str
    reason: str
    suggestion: str


class CompletionActionInfo(BaseModel):
    issue_title: str
    action_type: str
    query_or_request: str
    rationale: str


class WebCompletionRequest(BaseModel):
    query: str
    limit: int = 3


class StagingItemInfo(BaseModel):
    staging_id: str
    title: str
    url: str
    summary: str
    content: str
    status: str
    created_at: str


class HealthReviewResponse(BaseModel):
    report_markdown: str
    issues: list[HealthIssueInfo]
    completion_actions: list[CompletionActionInfo]


class SystemLogInfo(BaseModel):
    log_id: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    created_at: str


class InteractionFeedbackRequest(BaseModel):
    question: str
    answer_summary: str
    answer_type: str = "technical_explanation"
    user_feedback: str = ""
    user_action: str = "accepted"
    accepted: bool = True


class PreferenceCandidateInfo(BaseModel):
    candidate_id: str
    field: str
    old_value: str
    new_value: str
    evidence: str
    confidence: float
    status: str
    created_at: str


class GenerateResponse(BaseModel):
    kind: str
    content: str
