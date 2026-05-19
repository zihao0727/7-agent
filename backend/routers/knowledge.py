from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.auth_dependencies import require_current_user
from backend.knowledge_service import (
    delete_document,
    ingest_file,
    ingest_session,
    ingest_url,
    list_documents,
    search_knowledge,
)

router = APIRouter(tags=["knowledge"])


class IngestUrlRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000)


class IngestSessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)


class SearchKnowledgeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)


@router.get("/knowledge/documents")
async def get_knowledge_documents(current_user: dict = Depends(require_current_user)) -> dict:
    return {"documents": await list_documents(int(current_user["id"]))}


@router.post("/knowledge/upload")
async def upload_knowledge_files(
    files: Annotated[list[UploadFile], File(description="One or more files to index")],
    current_user: dict = Depends(require_current_user),
) -> dict:
    documents = []
    for file in files:
        raw = await file.read()
        try:
            documents.append(
                await ingest_file(
                    user_id=int(current_user["id"]),
                    filename=file.filename or "uploaded-file",
                    content_type=file.content_type or "application/octet-stream",
                    raw=raw,
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to ingest {file.filename or 'file'}: {exc}",
            ) from exc
    return {"documents": documents}


@router.post("/knowledge/url")
async def add_knowledge_url(
    req: IngestUrlRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    try:
        document = await ingest_url(user_id=int(current_user["id"]), url=req.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to ingest URL: {exc}") from exc
    return {"document": document}


@router.post("/knowledge/session")
async def add_knowledge_session(
    req: IngestSessionRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    try:
        document = await ingest_session(
            user_id=int(current_user["id"]),
            session_id=req.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"document": document}


@router.post("/knowledge/search")
async def search_knowledge_route(
    req: SearchKnowledgeRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    return {
        "results": await search_knowledge(
            int(current_user["id"]),
            req.query,
            limit=req.limit,
        )
    }


@router.delete("/knowledge/documents/{document_id}")
async def remove_knowledge_document(
    document_id: str,
    current_user: dict = Depends(require_current_user),
) -> dict:
    deleted = await delete_document(int(current_user["id"]), document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return {"id": document_id}
