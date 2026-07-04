from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Header, UploadFile

from backend.app.schemas import BatchUploadResponse, CardInfo, SourceInfo, UploadResponse
from backend.app.services import get_store, settings_with_model_overrides
from tracewiki.ingest import ingest_path

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    x_llm_api_key: Annotated[str | None, Header(alias="X-LLM-Api-Key")] = None,
    x_llm_base_url: Annotated[str | None, Header(alias="X-LLM-Base-Url")] = None,
    x_llm_text_model: Annotated[str | None, Header(alias="X-LLM-Text-Model")] = None,
    x_llm_vision_model: Annotated[str | None, Header(alias="X-LLM-Vision-Model")] = None,
    x_llm_embedding_model: Annotated[str | None, Header(alias="X-LLM-Embedding-Model")] = None,
) -> UploadResponse:
    settings = settings_with_model_overrides(
        api_key=x_llm_api_key,
        base_url=x_llm_base_url,
        text_model=x_llm_text_model,
        vision_model=x_llm_vision_model,
        embedding_model=x_llm_embedding_model,
    )
    card = ingest_path(await uploaded_file_to_temp_path(file), settings, get_store())
    return UploadResponse(card=CardInfo(**card.__dict__), message=f"Generated Wiki card: {card.title}")


@router.post("/upload/batch", response_model=BatchUploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    x_llm_api_key: Annotated[str | None, Header(alias="X-LLM-Api-Key")] = None,
    x_llm_base_url: Annotated[str | None, Header(alias="X-LLM-Base-Url")] = None,
    x_llm_text_model: Annotated[str | None, Header(alias="X-LLM-Text-Model")] = None,
    x_llm_vision_model: Annotated[str | None, Header(alias="X-LLM-Vision-Model")] = None,
    x_llm_embedding_model: Annotated[str | None, Header(alias="X-LLM-Embedding-Model")] = None,
) -> BatchUploadResponse:
    settings = settings_with_model_overrides(
        api_key=x_llm_api_key,
        base_url=x_llm_base_url,
        text_model=x_llm_text_model,
        vision_model=x_llm_vision_model,
        embedding_model=x_llm_embedding_model,
    )
    cards = []
    for file in files:
        card = ingest_path(await uploaded_file_to_temp_path(file), settings, get_store())
        cards.append(card)
    return BatchUploadResponse(
        cards=[CardInfo(**card.__dict__) for card in cards],
        message=f"Generated {len(cards)} Wiki cards",
    )


@router.get("/sources", response_model=list[SourceInfo])
def list_sources() -> list[SourceInfo]:
    return [SourceInfo(**item.__dict__) for item in get_store().list_sources()]


async def uploaded_file_to_temp_path(file: UploadFile) -> Path:
    suffix = Path(file.filename or "upload.txt").suffix
    raw = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        return Path(tmp.name)
