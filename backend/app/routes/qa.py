from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from backend.app.schemas import AskRequest, AskResponse, EvidenceResult, QASessionInfo
from backend.app.services import get_memory_service, get_store, settings_with_model_overrides
from tracewiki.evidence_graph import build_evidence_graph, result_table
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.models import QASession
from tracewiki.personalization import load_profile
from tracewiki.qa import answer_question
from tracewiki.reranker import rerank_results
from tracewiki.system_log import record_event
from tracewiki.wiki_builder import stable_id
from tracewiki.wiki_agent import wiki_guided_results
from tracewiki.wiki_maintenance import propose_answer_capture

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    x_llm_api_key: Annotated[str | None, Header(alias="X-LLM-Api-Key")] = None,
    x_llm_base_url: Annotated[str | None, Header(alias="X-LLM-Base-Url")] = None,
    x_llm_text_model: Annotated[str | None, Header(alias="X-LLM-Text-Model")] = None,
    x_llm_vision_model: Annotated[str | None, Header(alias="X-LLM-Vision-Model")] = None,
    x_llm_embedding_model: Annotated[str | None, Header(alias="X-LLM-Embedding-Model")] = None,
) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    user_id = payload.user_id.strip() or "default"

    store = get_store()
    settings = settings_with_model_overrides(
        api_key=x_llm_api_key,
        base_url=x_llm_base_url,
        text_model=x_llm_text_model,
        vision_model=x_llm_vision_model,
        embedding_model=x_llm_embedding_model,
    )
    profile = load_profile(settings.data_dir / "user_profile.json")
    cards = store.list_cards()
    spans = store.list_spans()
    vectors = store.list_vectors()
    client = ModelClient(settings)
    record_event(
        store,
        "question_received",
        "Received user question",
        {"user_id": user_id, "question": question, "card_count": len(cards), "span_count": len(spans), "vector_count": len(vectors)},
    )
    results = HybridRetriever(cards, spans, vectors, client).search(question, limit=max(payload.top_k * 3, 10))
    results = rerank_results(question, results, client, limit=payload.top_k)
    results = wiki_guided_results(question, cards, results, settings.wiki_dir, limit=max(payload.top_k + 3, 8), client=client)
    record_event(
        store,
        "retrieval_completed",
        f"Retrieved, reranked, and wiki-guided {len(results)} evidence items",
        {
            "result_titles": [item.title for item in results],
            "rerank_enabled": settings.rerank_enabled,
            "wiki_guided": True,
        },
    )
    memory_service = get_memory_service()
    memories = memory_service.search(user_id=user_id, query=question)
    if memories:
        record_event(
            store,
            "memory_retrieval_completed",
            f"Retrieved {len(memories)} user memories",
            {"user_id": user_id, "memory_ids": [item.memory_id for item in memories]},
        )
    answer = answer_question(question, results, profile, client, memories=memories)
    proposals = propose_answer_capture(question, answer.text, cards, client)
    for proposal in proposals:
        store.add_wiki_proposal(proposal)
    record_event(
        store,
        "answer_generated",
        "Generated source-grounded answer",
        {
            "claim_count": len(answer.claims),
            "answer_length": len(answer.text),
            "llm_answer_capture_proposals": len(proposals),
        },
        client=client,
    )
    claims = [
        {"text": claim.text, "confidence": claim.confidence, "evidence": claim.evidence}
        for claim in answer.claims
    ]
    graph_mermaid = build_evidence_graph(question, answer)
    evidence = [EvidenceResult(**row) for row in result_table(results)]
    evidence_payload = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in evidence]
    store.add_qa_session(
        QASession(
            session_id=stable_id("qa|" + question + "|" + answer.text[:200]),
            question=question,
            answer=answer.text,
            evidence=evidence_payload,
            graph_mermaid=graph_mermaid,
        )
    )
    memory_updates = memory_service.extract_and_update(user_id=user_id, question=question, answer=answer.text)
    if memory_updates:
        record_event(
            store,
            "memory_updated",
            f"Updated {len(memory_updates)} user memories from this QA turn",
            {"user_id": user_id, "memory_ids": [item.memory_id for item in memory_updates]},
        )
    return AskResponse(
        answer=answer.text,
        claims=claims,
        graph_mermaid=graph_mermaid,
        evidence=evidence,
        memories=[item.__dict__ for item in memories],
        memory_updates=[item.__dict__ for item in memory_updates],
    )


@router.get("/sessions", response_model=list[QASessionInfo])
def list_qa_sessions() -> list[QASessionInfo]:
    return [QASessionInfo(**session.__dict__) for session in get_store().list_qa_sessions()]
