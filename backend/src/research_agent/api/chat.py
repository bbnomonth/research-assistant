from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from research_agent.schemas.chat import ChatRequest
from research_agent.services.conversations import ConversationService


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
def stream_chat(payload: ChatRequest, request: Request):
    model_gateway = request.app.state.model_gateway
    if model_gateway is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "尚未配置百炼 API Key。请在 backend/.env 中填写"
                " DASHSCOPE_API_KEY 后重启服务。"
            ),
        )

    async def event_generator():
        database = request.app.state.database
        with database.session_factory() as db:
            service = ConversationService(db=db, model_gateway=model_gateway)
            async for event in service.stream_reply(
                content=payload.content,
                project_id=payload.project_id,
                session_id=payload.session_id,
                mode_override=payload.mode_override,
            ):
                yield event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

