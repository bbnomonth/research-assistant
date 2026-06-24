from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from research_agent.api.chat import router as chat_router
from research_agent.api.health import router as health_router
from research_agent.config import Settings
from research_agent.db.engine import Database
from research_agent.services.model_gateway import (
    ModelGateway,
    QwenOpenAIGateway,
)


def create_app(
    settings: Optional[Settings] = None,
    model_gateway: Optional[ModelGateway] = None,
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

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.create_schema()
        yield
        database.engine.dispose()

    app = FastAPI(
        title="Research Training Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.model_gateway = model_gateway
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
