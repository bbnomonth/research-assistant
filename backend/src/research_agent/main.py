from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

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
    LangChainArxivSearchProvider,
)
from research_agent.services.arxiv_import import HttpxPdfDownloader, PdfDownloader
from research_agent.repositories.tasks import TaskRepository


def create_app(
    settings: Optional[Settings] = None,
    model_gateway: Optional[ModelGateway] = None,
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
    if arxiv_provider is None:
        arxiv_provider = LangChainArxivSearchProvider(max_results=20)
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
            db.commit()
        try:
            yield
        finally:
            if model_gateway is not None:
                close = getattr(model_gateway, "aclose", None)
                if close is not None:
                    await close()
            database.engine.dispose()

    app = FastAPI(
        title="Research Training Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.model_gateway = model_gateway
    app.state.arxiv_provider = arxiv_provider
    app.state.ocr_service = ocr_service
    app.state.pdf_downloader = pdf_downloader
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(papers_router)
    app.include_router(artifacts_router)
    app.include_router(projects_router)
    app.include_router(system_router)
    return app


app = create_app()
