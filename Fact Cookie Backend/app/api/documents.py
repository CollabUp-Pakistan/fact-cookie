"""Document upload/list/delete routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=201)
async def upload_document(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    filename: Annotated[str | None, Form()] = None,
):
    data = await file.read()
    name = filename or file.filename or "document"
    document = await document_service.upload_document(db, user, name, file.content_type or "application/octet-stream", data)
    return {
        "id": document.id,
        "filename": document.filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "page_count": document.page_count,
        "status": document.status,
        "created_at": document.created_at.isoformat(),
    }


@router.get("")
async def list_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    documents = await document_service.list_documents(db, user)
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "size_bytes": d.size_bytes,
            "page_count": d.page_count,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }
        for d in documents
    ]


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await document_service.delete_document(db, user, document_id)
