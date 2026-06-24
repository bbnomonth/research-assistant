from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fitz
from fastapi import APIRouter, Request

from research_agent.schemas.system import (
    DiagnosticResponse,
    RuntimeSettingsResponse,
)
from research_agent.services.model_gateway import collect_chat


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(request: Request):
    settings = request.app.state.settings
    return {
        "model_configured": settings.model_configured,
        "qwen_model": settings.qwen_model,
        "qwen_base_url": settings.qwen_base_url,
        "ocr_configured": request.app.state.ocr_service is not None,
        "ocr_language": settings.ocr_language,
        "pdf_max_bytes": settings.pdf_max_bytes,
        "pdf_max_pages": settings.pdf_max_pages,
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
