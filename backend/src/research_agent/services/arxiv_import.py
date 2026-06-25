from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from research_agent.db.models import Paper, Task
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.tasks import TaskRepository
from research_agent.services.pdf_processing import OcrService, PdfProcessor


class PdfDownloader(Protocol):
    def download(
        self,
        url: str,
        destination: Path,
        max_bytes: int,
    ) -> None:
        pass


class HttpxPdfDownloader:
    def download(
        self,
        url: str,
        destination: Path,
        max_bytes: int,
    ) -> None:
        total = 0
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "ResearchTrainingAgent/0.1"},
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("download exceeds size limit")
                    output.write(chunk)


@dataclass(frozen=True)
class ArxivImportResult:
    task: Task
    stored_path: Path
    chunk_count: int


class ArxivPdfImportService:
    def __init__(
        self,
        db: Session,
        upload_dir: Path,
        downloader: PdfDownloader,
        max_bytes: int = 10 * 1024 * 1024,
        max_pages: int = 60,
        ocr_service: Optional[OcrService] = None,
        scrub_pii_enabled: bool = False,
    ) -> None:
        self.db = db
        self.upload_dir = upload_dir
        self.downloader = downloader
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.ocr_service = ocr_service
        self.scrub_pii_enabled = scrub_pii_enabled

    def import_pdf(self, paper_id: str) -> ArxivImportResult:
        return self.import_pdf_for_task(paper_id, task_id=None)

    def import_pdf_for_task(
        self,
        paper_id: str,
        task_id: Optional[str] = None,
    ) -> ArxivImportResult:
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            raise LookupError("paper not found")
        if paper.arxiv_id.startswith("upload:"):
            raise ValueError("uploaded papers cannot be imported from URL")
        parsed = urlparse(paper.pdf_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("paper PDF URL must use HTTP or HTTPS")

        task_repo = TaskRepository(self.db)
        if task_id is None:
            task = task_repo.create_task("import_arxiv_pdf", paper_id=paper.id)
        else:
            task = self.db.get(Task, task_id)
            if task is None or task.paper_id != paper.id:
                raise LookupError("task not found for paper")
            if task.status == "cancelled":
                raise ValueError("task was cancelled")
        task_repo.update_status(task.id, "processing", progress=10)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.upload_dir / f"{uuid4()}.pdf"
        try:
            self.downloader.download(
                paper.pdf_url,
                stored_path,
                self.max_bytes,
            )
            if not stored_path.exists():
                raise ValueError("PDF download did not create a file")
            if stored_path.stat().st_size > self.max_bytes:
                raise ValueError("download exceeds size limit")
            if not stored_path.read_bytes()[:5].startswith(b"%PDF-"):
                raise ValueError("downloaded content is not a PDF")
            chunks = PdfProcessor(
                max_bytes=self.max_bytes,
                ocr_service=self.ocr_service,
                scrub_pii_enabled=self.scrub_pii_enabled,
            ).extract_text_chunks(
                stored_path,
                max_pages=self.max_pages,
            )
            self.db.refresh(task)
            if task.status == "cancelled":
                raise ValueError("task was cancelled")
            PaperChunkRepository(self.db).replace_chunks(paper.id, chunks)
            paper.pdf_url = str(stored_path)
            task_repo.update_status(task.id, "completed", progress=100)
            return ArxivImportResult(
                task=task,
                stored_path=stored_path,
                chunk_count=len(chunks),
            )
        except Exception:
            if stored_path.exists():
                stored_path.unlink()
            self.db.refresh(task)
            if task.status != "cancelled":
                task_repo.update_status(
                    task.id,
                    "failed",
                    progress=0,
                    error_message="PDF import failed",
                )
            raise
