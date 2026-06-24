from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from research_agent.db.models import PaperChunk


@dataclass(frozen=True)
class EvidenceResult:
    chunk_id: str
    page_number: int
    section: str
    text: str
    is_ocr: bool


class PaperChunkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_chunks(
        self,
        paper_id: str,
        chunks: List[Dict],
    ) -> List[PaperChunk]:
        self.db.execute(
            text("DELETE FROM paper_chunks_fts WHERE paper_id = :paper_id"),
            {"paper_id": paper_id},
        )
        self.db.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper_id))
        stored = []
        for raw in chunks:
            chunk = PaperChunk(
                paper_id=paper_id,
                page_number=raw["page_number"],
                chunk_index=raw["chunk_index"],
                section=raw.get("section") or "",
                text=raw["text"],
                is_ocr=1 if raw.get("is_ocr") else 0,
            )
            self.db.add(chunk)
            self.db.flush()
            self.db.execute(
                text(
                    "INSERT INTO paper_chunks_fts(chunk_id, paper_id, text) "
                    "VALUES (:chunk_id, :paper_id, :text)"
                ),
                {
                    "chunk_id": chunk.id,
                    "paper_id": paper_id,
                    "text": chunk.text,
                },
            )
            stored.append(chunk)
        self.db.flush()
        return stored

    def search(
        self,
        paper_id: str,
        query: str,
        limit: int = 10,
    ) -> List[EvidenceResult]:
        rows = self.db.execute(
            text(
                "SELECT chunk_id FROM paper_chunks_fts "
                "WHERE paper_id = :paper_id AND text MATCH :query "
                "LIMIT :limit"
            ),
            {"paper_id": paper_id, "query": query, "limit": limit},
        ).mappings()
        ids = [row["chunk_id"] for row in rows]
        if not ids:
            return []
        chunks = list(
            self.db.scalars(
                select(PaperChunk)
                .where(PaperChunk.id.in_(ids))
                .order_by(PaperChunk.page_number, PaperChunk.chunk_index)
            )
        )
        return [
            EvidenceResult(
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                section=chunk.section,
                text=chunk.text,
                is_ocr=bool(chunk.is_ocr),
            )
            for chunk in chunks
        ]

    def list_for_paper(
        self,
        paper_id: str,
        limit: int = 8,
    ) -> List[EvidenceResult]:
        chunks = list(
            self.db.scalars(
                select(PaperChunk)
                .where(PaperChunk.paper_id == paper_id)
                .order_by(PaperChunk.page_number, PaperChunk.chunk_index)
                .limit(limit)
            )
        )
        return [
            EvidenceResult(
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                section=chunk.section,
                text=chunk.text,
                is_ocr=bool(chunk.is_ocr),
            )
            for chunk in chunks
        ]
