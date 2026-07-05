from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from backend.app.schemas import InteractionFeedbackRequest, MemoryCreateRequest, MemoryInfo, MemoryUpdateRequest, PreferenceCandidateInfo
from backend.app.services import get_memory_service, get_settings, get_store
from tracewiki.personalization import apply_candidate, load_profile, save_profile
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.system_log import record_event

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/profile")
def get_profile() -> dict:
    settings = get_settings()
    return asdict(load_profile(settings.data_dir / "user_profile.json"))


@router.post("/feedback")
def save_feedback(payload: InteractionFeedbackRequest) -> dict:
    store = get_store()
    user_id = payload.user_id.strip() or "default"
    log = create_interaction_log(
        question=payload.question,
        answer_summary=payload.answer_summary,
        answer_type=payload.answer_type,
        user_feedback=payload.user_feedback,
        user_action=payload.user_action,
        accepted=payload.accepted,
    )
    store.add_interaction(log)
    record_event(
        store,
        "interaction_feedback_saved",
        "Saved user feedback for preference distillation",
        {"user_action": payload.user_action, "accepted": payload.accepted},
    )
    memory_updates = get_memory_service().extract_and_update(
        user_id=user_id,
        question=payload.question,
        answer=payload.answer_summary,
        feedback=payload.user_feedback,
        action=payload.user_action,
        accepted=payload.accepted,
    )
    if memory_updates:
        record_event(
            store,
            "memory_updated_from_feedback",
            f"Updated {len(memory_updates)} user memories from explicit feedback",
            {"user_id": user_id, "memory_ids": [item.memory_id for item in memory_updates]},
        )
    return {"status": "ok", "log_id": log.log_id, "memory_updates": len(memory_updates)}


@router.get("/interactions")
def list_interactions() -> list[dict]:
    return [asdict(log) for log in get_store().list_interactions(limit=30)]


@router.post("/distill", response_model=list[PreferenceCandidateInfo])
def distill() -> list[PreferenceCandidateInfo]:
    store = get_store()
    settings = get_settings()
    profile = load_profile(settings.data_dir / "user_profile.json")
    candidates = distill_preferences(store.list_interactions(limit=30), profile)
    for candidate in candidates:
        store.add_preference_candidate(candidate)
    if candidates:
        record_event(
            store,
            "preference_distilled",
            f"Created {len(candidates)} preference candidates",
            {"candidate_fields": [item.field for item in candidates]},
        )
    return [PreferenceCandidateInfo(**candidate.__dict__) for candidate in candidates]


@router.get("/candidates", response_model=list[PreferenceCandidateInfo])
def list_candidates() -> list[PreferenceCandidateInfo]:
    return [
        PreferenceCandidateInfo(**candidate.__dict__)
        for candidate in get_store().list_preference_candidates(status="pending")
    ]


@router.post("/candidates/{candidate_id}/accept")
def accept_candidate(candidate_id: str) -> dict[str, str]:
    store = get_store()
    settings = get_settings()
    candidates = [item for item in store.list_preference_candidates() if item.candidate_id == candidate_id]
    if not candidates:
        raise HTTPException(status_code=404, detail="Candidate not found")
    profile_path = settings.data_dir / "user_profile.json"
    profile = apply_candidate(load_profile(profile_path), candidates[0])
    save_profile(profile_path, profile)
    store.update_candidate_status(candidate_id, "accepted")
    record_event(
        store,
        "preference_candidate_accepted",
        f"Accepted preference candidate {candidates[0].field}",
        {"field": candidates[0].field, "new_value": candidates[0].new_value},
    )
    return {"status": "accepted"}


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str) -> dict[str, str]:
    get_store().update_candidate_status(candidate_id, "rejected")
    return {"status": "rejected"}


@router.get("/memories", response_model=list[MemoryInfo])
def list_memories(user_id: str = "default") -> list[MemoryInfo]:
    memories = get_memory_service().list(user_id=user_id.strip() or "default", status="active", limit=100)
    return [MemoryInfo(**item.__dict__) for item in memories]


@router.get("/memories/search", response_model=list[MemoryInfo])
def search_memories(query: str, user_id: str = "default", limit: int = 5) -> list[MemoryInfo]:
    memories = get_memory_service().search(user_id=user_id.strip() or "default", query=query, limit=limit)
    return [MemoryInfo(**item.__dict__) for item in memories]


@router.post("/memories", response_model=MemoryInfo)
def add_memory(payload: MemoryCreateRequest) -> MemoryInfo:
    memory = get_memory_service().add(
        user_id=payload.user_id.strip() or "default",
        memory_type=payload.memory_type,
        content=payload.content,
        metadata=payload.metadata,
        confidence=payload.confidence,
        source=payload.source,
    )
    return MemoryInfo(**memory.__dict__)


@router.patch("/memories/{memory_id}", response_model=MemoryInfo)
def update_memory(memory_id: str, payload: MemoryUpdateRequest) -> MemoryInfo:
    memory = get_memory_service().update(
        memory_id,
        content=payload.content,
        metadata=payload.metadata,
        confidence=payload.confidence,
        status=payload.status,
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryInfo(**memory.__dict__)


@router.delete("/memories/{memory_id}", response_model=dict[str, str])
def delete_memory(memory_id: str) -> dict[str, str]:
    if not get_memory_service().delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted"}
