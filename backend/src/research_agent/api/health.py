from fastapi import APIRouter, Request
from sqlalchemy import text


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
        "model_configured": request.app.state.settings.model_configured,
    }

