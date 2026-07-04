from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header

from backend.app.schemas import CompletionActionInfo, HealthIssueInfo, HealthReviewResponse
from backend.app.services import get_store
from backend.app.services import settings_with_model_overrides
from tracewiki.completion import propose_completion_actions
from tracewiki.health_check import render_health_report, review_knowledge_base
from tracewiki.llm import ModelClient
from tracewiki.system_log import record_event

router = APIRouter(prefix="/health", tags=["review"])


@router.get("/review", response_model=HealthReviewResponse)
def review_knowledge(
    x_llm_api_key: Annotated[str | None, Header(alias="X-LLM-Api-Key")] = None,
    x_llm_base_url: Annotated[str | None, Header(alias="X-LLM-Base-Url")] = None,
    x_llm_text_model: Annotated[str | None, Header(alias="X-LLM-Text-Model")] = None,
    x_llm_vision_model: Annotated[str | None, Header(alias="X-LLM-Vision-Model")] = None,
    x_llm_embedding_model: Annotated[str | None, Header(alias="X-LLM-Embedding-Model")] = None,
) -> HealthReviewResponse:
    store = get_store()
    settings = settings_with_model_overrides(
        api_key=x_llm_api_key,
        base_url=x_llm_base_url,
        text_model=x_llm_text_model,
        vision_model=x_llm_vision_model,
        embedding_model=x_llm_embedding_model,
    )
    client = ModelClient(settings)
    issues = review_knowledge_base(store.list_cards(), client=client)
    actions = propose_completion_actions(issues)
    record_event(
        store,
        "health_review_completed",
        f"Knowledge health review found {len(issues)} issues",
        {"issue_titles": [issue.title for issue in issues]},
        client=client,
    )
    return HealthReviewResponse(
        report_markdown=render_health_report(issues),
        issues=[HealthIssueInfo(**issue.__dict__) for issue in issues],
        completion_actions=[CompletionActionInfo(**action.__dict__) for action in actions],
    )
