from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from research_agent.db.models import Paper
from research_agent.db.models import Task
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.tasks import TaskRepository
from research_agent.schemas.papers import EvidenceSearchResponse, UploadResponse
from research_agent.services.pdf_processing import PdfProcessor, PdfTooLargeError


router = APIRouter(prefix="/api", tags=["papers"])


@router.post("/papers/upload", response_model=UploadResponse)
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    settings = request.app.state.settings
    content = await file.read()
    if len(content) > settings.pdf_max_bytes:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MB limit.")

    upload_dir = settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid4()}.pdf"
    stored_path.write_bytes(content)

    database = request.app.state.database
    with database.session_factory() as db:
        paper = Paper(
            project_id=_ensure_upload_project(db),
            arxiv_id=f"upload:{stored_path.stem}",
            title=file.filename,
            authors_json="[]",
            abstract="",
            published="",
            categories_json="[]",
            entry_url=str(stored_path),
            pdf_url=str(stored_path),
        )
        db.add(paper)
        db.flush()
        task_repo = TaskRepository(db)
        task = task_repo.create_task("parse_pdf", paper_id=paper.id)
        try:
            chunks = PdfProcessor(
                max_bytes=settings.pdf_max_bytes
            ).extract_text_chunks(stored_path, max_pages=settings.pdf_max_pages)
            PaperChunkRepository(db).replace_chunks(paper.id, chunks)
            task_repo.update_status(task.id, "completed", progress=100)
        except PdfTooLargeError as exc:
            task_repo.update_status(
                task.id,
                "failed",
                progress=0,
                error_message=str(exc),
            )
            db.commit()
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            task_repo.update_status(
                task.id,
                "failed",
                progress=0,
                error_message="PDF parsing failed.",
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="PDF parsing failed.",
            ) from exc
        db.commit()
        return {
            "paper_id": paper.id,
            "task": {
                "id": task.id,
                "status": task.status,
                "progress": task.progress,
                "error_message": task.error_message,
            },
        }


@router.get("/papers/{paper_id}/evidence", response_model=EvidenceSearchResponse)
def search_evidence(paper_id: str, q: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        results = PaperChunkRepository(db).search(paper_id, q)
        return {"results": [item.__dict__ for item in results]}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return {
            "id": task.id,
            "status": task.status,
            "progress": task.progress,
            "error_message": task.error_message,
        }


def _ensure_upload_project(db) -> str:
    from research_agent.repositories.conversations import ConversationRepository

    project, _ = ConversationRepository(db).ensure_conversation(None, None)
    return project.id
