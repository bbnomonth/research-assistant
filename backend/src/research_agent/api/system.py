from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fitz
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from research_agent.db.models import (
    Artifact,
    ConversationSession,
    Message,
    ModelCallLog,
    Paper,
    PaperChunk,
    Project,
    Task,
)
from research_agent.schemas.system import (
    DiagnosticResponse,
    PrivacySettingsResponse,
    RuntimeSettingsResponse,
    WipeDataResponse,
)
from research_agent.services.model_gateway import collect_chat


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(request: Request):
    settings = request.app.state.settings
    privacy = request.app.state.privacy
    return {
        "model_configured": settings.model_configured,
        "qwen_model": settings.qwen_model,
        "qwen_base_url": settings.qwen_base_url,
        "ocr_configured": request.app.state.ocr_service is not None,
        "ocr_language": settings.ocr_language,
        "pdf_max_bytes": settings.pdf_max_bytes,
        "pdf_max_pages": settings.pdf_max_pages,
        "privacy": PrivacySettingsResponse(
            pii_scrub=privacy["pii_scrub"],
            local_only=privacy["local_only"],
            data_ttl_days=privacy["data_ttl_days"],
        ),
    }


@router.post("/wipe-data", response_model=WipeDataResponse)
def wipe_user_data(request: Request):
    """Remove uploaded files and wipe database content.

    Intended to give the user a single-click privacy reset.  The
    configuration (settings, API key) is preserved so the application
    remains usable afterwards.
    """

    settings = request.app.state.settings
    database = request.app.state.database

    upload_dir = settings.resolved_upload_dir
    removed_uploads = 0
    if upload_dir.exists():
        for entry in upload_dir.iterdir():
            try:
                if entry.is_file() and not entry.name.startswith("."):
                    entry.unlink()
                    removed_uploads += 1
                elif entry.is_dir():
                    for child in entry.rglob("*"):
                        if child.is_file():
                            child.unlink()
                            removed_uploads += 1
                    for child in sorted(entry.rglob("*"), reverse=True):
                        if child.is_dir():
                            child.rmdir()
                    entry.rmdir()
            except OSError:
                # Best-effort cleanup; continue even if some files are
                # locked by the OS or another process.
                continue

    removed_messages = 0
    removed_sessions = 0
    removed_projects = 0
    with database.session_factory() as db:
        try:
            removed_messages = db.query(Message).delete(synchronize_session=False)
            db.execute(text("DELETE FROM paper_chunks_fts"))
            db.query(PaperChunk).delete(synchronize_session=False)
            db.query(Task).delete(synchronize_session=False)
            db.query(Artifact).delete(synchronize_session=False)
            db.query(Paper).delete(synchronize_session=False)
            db.query(ModelCallLog).delete(synchronize_session=False)
            removed_sessions = (
                db.query(ConversationSession).delete(synchronize_session=False)
            )
            removed_projects = db.query(Project).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="database wipe failed")

    return {
        "wiped": True,
        "removed_uploads": removed_uploads,
        "removed_messages": removed_messages,
        "removed_sessions": removed_sessions,
        "removed_projects": removed_projects,
        "message": "已清除全部上传文件、论文、会话和消息记录；配置保持不变。",
    }


@router.post("/check-storage", response_model=DiagnosticResponse)
def check_storage(request: Request):
    directory = request.app.state.settings.resolved_upload_dir
    probe = directory / f".storage-probe-{uuid4()}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="ascii")
        probe.read_text(encoding="ascii")
        return {
            "available": True,
            "message": "Storage directory is writable.",
        }
    except OSError:
        return {
            "available": False,
            "message": "Storage directory is not writable.",
        }
    finally:
        if probe.exists():
            probe.unlink()


@router.post("/check-ocr", response_model=DiagnosticResponse)
def check_ocr(request: Request):
    service = request.app.state.ocr_service
    if service is None:
        return {
            "configured": False,
            "available": False,
            "message": "OCR service is not configured.",
        }

    upload_dir = request.app.state.settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(dir=upload_dir) as temp_dir:
            image_path = Path(temp_dir) / "ocr-probe.png"
            document = fitz.open()
            page = document.new_page(width=300, height=100)
            page.insert_text((20, 50), "OCR probe")
            page.get_pixmap().save(image_path)
            document.close()
            service.ocr_image(image_path)
        return {
            "configured": True,
            "available": True,
            "message": "OCR service is available.",
        }
    except Exception:
        return {
            "configured": True,
            "available": False,
            "message": "OCR service check failed.",
        }


@router.post("/check-model", response_model=DiagnosticResponse)
async def check_model(request: Request):
    gateway = request.app.state.model_gateway
    if gateway is None:
        return {
            "configured": False,
            "available": False,
            "message": "Model gateway is not configured.",
        }
    try:
        await collect_chat(
            gateway,
            [{"role": "user", "content": "Reply with OK for a health check."}],
        )
        return {
            "configured": True,
            "available": True,
            "message": "Model gateway is available.",
        }
    except Exception:
        return {
            "configured": True,
            "available": False,
            "message": "Model gateway check failed.",
        }
