from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from research_agent.db.models import Paper
from research_agent.db.models import Task
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.tasks import TaskRepository
from research_agent.schemas.papers import (
    EvidenceSearchResponse,
    PaperComparisonRequest,
    PaperComparisonResponse,
    QuickAnalysisResponse,
    UploadResponse,
)
from research_agent.services.paper_analysis import PaperAnalysisService
from research_agent.services.arxiv_import import ArxivPdfImportService
from research_agent.services.pdf_processing import PdfProcessor, PdfTooLargeError


router = APIRouter(prefix="/api", tags=["papers"])


@router.post("/papers/upload", response_model=UploadResponse)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(default=None),
):
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
        try:
            upload_project_id = _ensure_upload_project(db, project_id)
        except LookupError as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        paper = Paper(
            project_id=upload_project_id,
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
        db.commit()
        background_tasks.add_task(
            _process_uploaded_pdf,
            request.app,
            task.id,
            paper.id,
            stored_path,
        )
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


@router.post("/papers/{paper_id}/import-pdf", response_model=UploadResponse)
def import_arxiv_pdf(
    paper_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    database = request.app.state.database
    with database.session_factory() as db:
        paper = db.get(Paper, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="paper not found")
        parsed = urlparse(paper.pdf_url)
        if paper.arxiv_id.startswith("upload:") or parsed.scheme not in {
            "http",
            "https",
        }:
            raise HTTPException(
                status_code=400,
                detail="paper does not have an importable arXiv PDF URL",
            )
        task = TaskRepository(db).create_task(
            "import_arxiv_pdf",
            paper_id=paper.id,
        )
        db.commit()
        background_tasks.add_task(
            _process_arxiv_pdf,
            request.app,
            task.id,
            paper.id,
        )
        return {
            "paper_id": paper_id,
            "task": {
                "id": task.id,
                "status": task.status,
                "progress": task.progress,
                "error_message": task.error_message,
            },
        }


@router.post(
    "/papers/{paper_id}/quick-analysis",
    response_model=QuickAnalysisResponse,
)
async def quick_analysis(paper_id: str, request: Request):
    model_gateway = request.app.state.model_gateway
    if model_gateway is None:
        raise HTTPException(
            status_code=503,
            detail="Model gateway is not configured.",
        )

    database = request.app.state.database
    with database.session_factory() as db:
        try:
            result = await PaperAnalysisService(
                db=db,
                model_gateway=model_gateway,
            ).quick_analyze(paper_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
        return {
            "artifact_id": result.artifact.id,
            "title": result.artifact.title,
            "evidence_pages": result.evidence_pages,
        }


@router.post("/papers/compare", response_model=PaperComparisonResponse)
async def compare_papers(payload: PaperComparisonRequest, request: Request):
    model_gateway = request.app.state.model_gateway
    if model_gateway is None:
        raise HTTPException(
            status_code=503,
            detail="Model gateway is not configured.",
        )

    database = request.app.state.database
    with database.session_factory() as db:
        try:
            result = await PaperAnalysisService(
                db=db,
                model_gateway=model_gateway,
            ).compare_papers(payload.paper_ids)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        db.commit()
        return {
            "artifact_id": result.artifact.id,
            "title": result.artifact.title,
            "evidence_pages": result.evidence_pages,
        }


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


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            task = TaskRepository(db).cancel(task_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        db.commit()
        return {
            "id": task.id,
            "status": task.status,
            "progress": task.progress,
            "error_message": task.error_message,
        }


@router.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            task = TaskRepository(db).retry(task_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        paper = db.get(Paper, task.paper_id) if task.paper_id else None
        db.commit()
        if task.task_type == "parse_pdf" and paper is not None:
            background_tasks.add_task(
                _process_uploaded_pdf,
                request.app,
                task.id,
                paper.id,
                Path(paper.pdf_url),
            )
        elif task.task_type == "import_arxiv_pdf" and paper is not None:
            background_tasks.add_task(
                _process_arxiv_pdf,
                request.app,
                task.id,
                paper.id,
            )
        return {
            "id": task.id,
            "status": task.status,
            "progress": task.progress,
            "error_message": task.error_message,
        }


def _ensure_upload_project(db, project_id: Optional[str] = None) -> str:
    from research_agent.repositories.conversations import ConversationRepository

    project, _ = ConversationRepository(db).ensure_conversation(
        project_id,
        None,
    )
    return project.id


def _process_uploaded_pdf(
    app,
    task_id: str,
    paper_id: str,
    stored_path: Path,
) -> None:
    settings = app.state.settings
    database = app.state.database
    with database.session_factory() as db:
        task_repo = TaskRepository(db)
        task = db.get(Task, task_id)
        if task is None or task.status == "cancelled":
            return
        task_repo.update_status(task.id, "processing", progress=10)
        db.commit()
        try:
            chunks = PdfProcessor(
                max_bytes=settings.pdf_max_bytes,
                ocr_service=app.state.ocr_service,
            ).extract_text_chunks(
                stored_path,
                max_pages=settings.pdf_max_pages,
            )
            db.refresh(task)
            if task.status == "cancelled":
                return
            PaperChunkRepository(db).replace_chunks(paper_id, chunks)
            task_repo.update_status(task.id, "completed", progress=100)
            db.commit()
        except PdfTooLargeError as exc:
            db.rollback()
            task = db.get(Task, task_id)
            if task is not None and task.status != "cancelled":
                task_repo.update_status(
                    task.id,
                    "failed",
                    progress=0,
                    error_message=str(exc),
                )
                db.commit()
        except Exception:
            db.rollback()
            task = db.get(Task, task_id)
            if task is not None and task.status != "cancelled":
                task_repo.update_status(
                    task.id,
                    "failed",
                    progress=0,
                    error_message="PDF parsing failed.",
                )
                db.commit()


def _process_arxiv_pdf(app, task_id: str, paper_id: str) -> None:
    settings = app.state.settings
    database = app.state.database
    with database.session_factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status == "cancelled":
            return
        try:
            TaskRepository(db).update_status(
                task.id,
                "processing",
                progress=10,
            )
            db.commit()
            ArxivPdfImportService(
                db=db,
                upload_dir=settings.resolved_upload_dir,
                downloader=app.state.pdf_downloader,
                max_bytes=settings.pdf_max_bytes,
                max_pages=settings.pdf_max_pages,
                ocr_service=app.state.ocr_service,
            ).import_pdf_for_task(paper_id, task_id)
            db.commit()
        except Exception:
            db.commit()
