from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from backend.app.schemas import CardInfo, KnowledgeGraphInfo, WikiPageInfo, WikiProposalInfo
from backend.app.services import get_store
from backend.app.services import get_settings
from backend.app.services import settings_with_model_overrides
from tracewiki.knowledge_graph import build_knowledge_graph
from tracewiki.llm import ModelClient
from tracewiki.models import KnowledgeCard, SourceSpan
from tracewiki.vector_index import build_vector_records
from tracewiki.wiki_builder import stable_id
from tracewiki.wiki_organizer import render_index_page

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("/cards", response_model=list[CardInfo])
def list_cards() -> list[CardInfo]:
    return [CardInfo(**card.__dict__) for card in get_store().list_cards()]


@router.get("/index", response_model=WikiPageInfo)
def get_index_page() -> WikiPageInfo:
    settings = get_settings()
    path = settings.wiki_dir / "index.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return WikiPageInfo(filename="index.md", content=content)


@router.get("/log", response_model=WikiPageInfo)
def get_log_page() -> WikiPageInfo:
    settings = get_settings()
    path = settings.wiki_dir / "log.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return WikiPageInfo(filename="log.md", content=content)


@router.get("/graph", response_model=KnowledgeGraphInfo)
def get_knowledge_graph() -> KnowledgeGraphInfo:
    store = get_store()
    graph = build_knowledge_graph(store.list_cards(), store.list_spans(limit=5000))
    return KnowledgeGraphInfo(**graph)


@router.delete("/cards/{card_id}", response_model=dict[str, str])
def delete_card(card_id: str) -> dict[str, str]:
    store = get_store()
    settings = settings_with_model_overrides()
    if not store.delete_card(card_id):
        raise HTTPException(status_code=404, detail="card not found")
    render_index_page(store.list_cards(), settings.wiki_dir)
    return {"status": "deleted"}


@router.get("/proposals", response_model=list[WikiProposalInfo])
def list_wiki_proposals() -> list[WikiProposalInfo]:
    return [WikiProposalInfo(**proposal.__dict__) for proposal in get_store().list_wiki_proposals(status="pending")]


@router.post("/proposals/{proposal_id}/accept", response_model=dict[str, str])
def accept_wiki_proposal(
    proposal_id: str,
    x_llm_api_key: Annotated[str | None, Header(alias="X-LLM-Api-Key")] = None,
    x_llm_base_url: Annotated[str | None, Header(alias="X-LLM-Base-Url")] = None,
    x_llm_text_model: Annotated[str | None, Header(alias="X-LLM-Text-Model")] = None,
    x_llm_vision_model: Annotated[str | None, Header(alias="X-LLM-Vision-Model")] = None,
    x_llm_embedding_model: Annotated[str | None, Header(alias="X-LLM-Embedding-Model")] = None,
) -> dict[str, str]:
    store = get_store()
    settings = settings_with_model_overrides(
        api_key=x_llm_api_key,
        base_url=x_llm_base_url,
        text_model=x_llm_text_model,
        vision_model=x_llm_vision_model,
        embedding_model=x_llm_embedding_model,
    )
    proposals = [proposal for proposal in store.list_wiki_proposals() if proposal.proposal_id == proposal_id]
    if not proposals:
        raise HTTPException(status_code=404, detail="proposal not found")
    proposal = proposals[0]
    cards = store.list_cards()
    if proposal.proposal_type == "update_page" and proposal.target_card_id:
        target = next((card for card in cards if card.card_id == proposal.target_card_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="target card not found")
        target.content = proposal.proposed_content
        store.upsert_card(target)
        target_spans = [span for span in store.list_spans() if span.card_id == target.card_id]
        store.upsert_vectors(build_vector_records(target, target_spans, ModelClient(settings)))
    elif proposal.proposal_type == "answer_capture":
        card = KnowledgeCard(
            card_id=stable_id("answer_capture|" + proposal.title + "|" + proposal.proposed_content[:200]),
            title=proposal.title,
            summary=proposal.rationale[:240],
            tags=["FAQ", "Captured Answer"],
            category="answer_capture",
            source_id="llm_answer_capture",
            source_path="llm://answer-capture",
            content=proposal.proposed_content,
            evidence=[{"source_path": "llm://answer-capture", "proposal_id": proposal.proposal_id}],
        )
        store.upsert_card(card)
        span = SourceSpan(
            span_id=stable_id("answer_capture_span|" + card.card_id),
            source_id=card.source_id,
            card_id=card.card_id,
            source_path=card.source_path,
            locator="answer_capture:1",
            text=card.content,
            span_type="answer_capture",
        )
        store.replace_spans_for_card(card.card_id, [span])
        store.upsert_vectors(build_vector_records(card, [span], ModelClient(settings)))
    store.update_wiki_proposal_status(proposal_id, "accepted")
    render_index_page(store.list_cards(), settings.wiki_dir)
    return {"status": "accepted"}


@router.post("/proposals/{proposal_id}/reject", response_model=dict[str, str])
def reject_wiki_proposal(proposal_id: str) -> dict[str, str]:
    store = get_store()
    proposals = [proposal for proposal in store.list_wiki_proposals() if proposal.proposal_id == proposal_id]
    if not proposals:
        raise HTTPException(status_code=404, detail="proposal not found")
    store.update_wiki_proposal_status(proposal_id, "rejected")
    return {"status": "rejected"}
