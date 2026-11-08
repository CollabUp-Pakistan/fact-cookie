"""Document service: upload, index, search, delete."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFoundError, PayloadTooLargeError, UnsupportedMediaTypeError
from app.db.models import Document, DocumentChunk, User
from app.retrieval.documents import extract_pages


async def upload_document(db: AsyncSession, user: User, filename: str, content_type: str, data: bytes) -> Document:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.document_allowed_extensions:
        raise UnsupportedMediaTypeError("Unsupported document type.")
    if len(data) > settings.document_max_bytes:
        raise PayloadTooLargeError("Document exceeds maximum size.")

    upload_dir = Path(settings.upload_dir) / str(user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid.uuid4().hex}{suffix}"
    storage_path = upload_dir / storage_name
    storage_path.write_bytes(data)

    document = Document(
        user_id=str(user.id),
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        storage_path=str(storage_path),
        status="processing",
    )
    db.add(document)
    await db.flush()

    try:
        pages = extract_pages(storage_path, filename)
        for page in pages:
            for chunk_index, chunk_text in enumerate(_chunk_page_text(page["text"])):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        user_id=str(user.id),
                        page_number=page["page_number"],
                        section=page.get("section"),
                        chunk_index=chunk_index,
                        content=chunk_text,
                    )
                )
        document.page_count = len(pages)
        document.status = "ready"
    except Exception as exc:
        document.status = "failed"
        document.error = str(exc)
    await db.commit()
    await db.refresh(document)
    return document


def _chunk_page_text(text: str) -> list[str]:
    if len(text) <= settings.document_chunk_chars:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + settings.document_chunk_chars, len(text))
        chunks.append(text[start:end])
        start = end - settings.document_chunk_overlap
        if start >= end:
            break
    return chunks


async def list_documents(db: AsyncSession, user: User) -> list[Document]:
    result = await db.execute(select(Document).where(Document.user_id == str(user.id)).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, user: User, document_id: str) -> None:
    result = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == str(user.id)))
    document = result.scalar_one_or_none()
    if not document:
        raise NotFoundError("Document not found.")
    path = Path(document.storage_path)
    if path.exists():
        path.unlink()
    await db.delete(document)
    await db.commit()


async def search_documents(db: AsyncSession, user: User, query: str, limit: int = 5) -> list[DocumentChunk]:
    terms = [t.lower() for t in query.split() if t.strip()]
    if not terms:
        return []
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == str(user.id))
        .order_by(DocumentChunk.created_at.desc())
        .limit(200)
    )
    chunks = list(result.scalars().all())
    scored = []
    for chunk in chunks:
        content = chunk.content.lower()
        score = sum(content.count(term) for term in terms)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]
