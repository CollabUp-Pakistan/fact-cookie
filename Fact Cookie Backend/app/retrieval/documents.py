"""Document extraction, chunking, indexing, and search."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from app.core.config import settings


_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 ,:'\-]{2,80})$")


def extract_pages(file_path: Path, filename: str) -> list[dict]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix in {".txt", ".md", ".markdown"}:
        return _extract_text(file_path)
    raise ValueError("Unsupported document type")


def _extract_pdf(file_path: Path) -> list[dict]:
    pages = []
    doc = fitz.open(file_path)
    try:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append({"page_number": index, "text": text, "section": _nearest_heading(text)})
    finally:
        doc.close()
    return pages


def _extract_text(file_path: Path) -> list[dict]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix.lower() in {".md", ".markdown"}:
        sections = _split_markdown_sections(text)
        return [{"page_number": i + 1, "text": section, "section": _nearest_heading(section)} for i, section in enumerate(sections)]
    chunks = _chunk_text(text, settings.document_chunk_chars, settings.document_chunk_overlap)
    return [{"page_number": i + 1, "text": chunk, "section": _nearest_heading(chunk)} for i, chunk in enumerate(chunks)]


def _split_markdown_sections(text: str) -> list[str]:
    parts = re.split(r"(?m)^(#{1,6}\s+.+)$", text)
    sections = []
    current = ""
    for part in parts:
        if part.startswith("#"):
            if current.strip():
                sections.append(current.strip())
            current = part + "\n"
        else:
            current += part
    if current.strip():
        sections.append(current.strip())
    return sections or [text]


def _chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 > chunk_chars and current:
            chunks.append(current.strip())
            current = current[-overlap:] + "\n\n" + paragraph
        else:
            current = (current + "\n\n" + paragraph).strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def _nearest_heading(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:300]
        if _HEADING_RE.match(line):
            return line[:300]
    return None
