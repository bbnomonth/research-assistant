from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from research_agent.api.artifacts import router as artifacts_router
from research_agent.api.chat import router as chat_router
from research_agent.api.health import router as health_router
from research_agent.api.papers import router as papers_router
from research_agent.api.projects import router as projects_router
from research_agent.api.system import router as system_router
from research_agent.config import Settings
from research_agent.db.engine import Database
from research_agent.services.model_gateway import (
    ModelGateway,
    QwenOpenAIGateway,
)
from research_agent.services.pdf_processing import OcrService, TesseractOcrService
from research_agent.services.arxiv_search import (
    ArxivSearchProvider,
    ArxivClientSearchProvider,
)
from research_agent.services.arxiv_import import HttpxPdfDownloader, PdfDownloader
from research_agent.repositories.tasks import TaskRepository
from research_agent.services.privacy import cleanup_expired_conversations


def create_app(
    settings: Optional[Settings] = None,
    model_gateway: Optional[ModelGateway] = None,
    router_model_gateway: Optional[ModelGateway] = None,
    arxiv_provider: Optional[ArxivSearchProvider] = None,
    ocr_service: Optional[OcrService] = None,
    pdf_downloader: Optional[PdfDownloader] = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    database = Database(active_settings.resolved_database_path)
    active_settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)

    if model_gateway is None and active_settings.model_configured:
        model_gateway = QwenOpenAIGateway(
            api_key=active_settings.qwen_api_key or "",
            base_url=active_settings.qwen_base_url,
            model_name=active_settings.qwen_model,
        )
    if router_model_gateway is None and active_settings.router_model_configured:
        router_extra_body = (
            {"enable_thinking": False}
            if active_settings.router_disable_thinking
            else None
        )
        router_model_gateway = QwenOpenAIGateway(
            api_key=active_settings.router_api_key or active_settings.qwen_api_key or "",
            base_url=active_settings.router_base_url,
            model_name=active_settings.router_model,
            max_output_tokens=256,
            extra_body=router_extra_body,
        )
    if arxiv_provider is None:
        arxiv_provider = ArxivClientSearchProvider(max_results=20)
    if ocr_service is None and active_settings.tesseract_executable:
        ocr_service = TesseractOcrService(
            executable=active_settings.tesseract_executable,
            language=active_settings.ocr_language,
        )
    if pdf_downloader is None:
        pdf_downloader = HttpxPdfDownloader()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.create_schema()
        with database.session_factory() as db:
            TaskRepository(db).mark_active_interrupted()
            cleanup_expired_conversations(
                db,
                active_settings.privacy_data_ttl_days,
            )
            db.commit()
        try:
            yield
        finally:
            if model_gateway is not None:
                close = getattr(model_gateway, "aclose", None)
                if close is not None:
                    await close()
            if router_model_gateway is not None and router_model_gateway is not model_gateway:
                close = getattr(router_model_gateway, "aclose", None)
                if close is not None:
                    await close()
            database.engine.dispose()

    app = FastAPI(
        title="Research Training Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.model_gateway = model_gateway
    app.state.router_model_gateway = router_model_gateway
    app.state.arxiv_provider = arxiv_provider
    app.state.ocr_service = ocr_service
    app.state.pdf_downloader = pdf_downloader
    app.state.privacy = {
        "pii_scrub": active_settings.privacy_pii_scrub,
        "local_only": active_settings.privacy_local_only,
        "data_ttl_days": active_settings.privacy_data_ttl_days,
    }
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(papers_router)
    app.include_router(artifacts_router)
    app.include_router(projects_router)
    app.include_router(system_router)
    return app


app = create_app()
