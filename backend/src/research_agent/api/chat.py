from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.conversations import ConversationRepository
from research_agent.schemas.artifacts import ArtifactResponse
from research_agent.schemas.chat import (
    ChatMode,
    ChatRequest,
    FrameworkCardRequest,
    TopicGuidanceCardRequest,
)
from research_agent.services.conversations import ConversationService
from research_agent.services.research_diagnosis import (
    FrameworkBuilder,
    is_framework_final_plan,
    render_framework_card_markdown,
)
from research_agent.services.topic_guidance import (
    TopicGuidanceService,
    is_topic_guidance_final_plan,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
def stream_chat(payload: ChatRequest, request: Request):
    model_gateway = request.app.state.model_gateway
    privacy = request.app.state.privacy
    if model_gateway is None and not privacy["local_only"]:
        detail = (
            "尚未配置百炼 API Key。请在 backend/.env 中填写"
            " DASHSCOPE_API_KEY 后重启服务。"
        )
        raise HTTPException(status_code=503, detail=detail)

    async def event_generator():
        database = request.app.state.database
        with database.session_factory() as db:
            service = ConversationService(
                db=db,
                model_gateway=model_gateway,
                arxiv_provider=request.app.state.arxiv_provider,
            )
            async for event in service.stream_reply(
                content=payload.content,
                project_id=payload.project_id,
                session_id=payload.session_id,
                paper_id=payload.paper_id,
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


@router.post("/framework/card", response_model=ArtifactResponse)
async def create_framework_card(payload: FrameworkCardRequest, request: Request):
    model_gateway = request.app.state.model_gateway
    privacy = request.app.state.privacy
    if model_gateway is None and not privacy["local_only"]:
        raise HTTPException(
            status_code=503,
            detail="搭建框架卡片需要调用大模型，请先配置 API Key 后重启服务。",
        )
    if model_gateway is None:
        raise HTTPException(
            status_code=503,
            detail="当前没有可用的大模型，暂时无法整理框架卡片。",
        )

    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        session_and_messages = repository.get_session_with_messages(
            payload.session_id,
        )
        if session_and_messages is None:
            raise HTTPException(status_code=404, detail="session not found")
        session, messages = session_and_messages
        if session.project_id != payload.project_id:
            raise HTTPException(status_code=404, detail="session not found")

        framework_replies = [
            message
            for message in messages
            if message.role == "assistant"
            and message.mode == ChatMode.FRAMEWORK_BUILDING.value
        ]
        if not framework_replies or not is_framework_final_plan(
            framework_replies[-1].content,
        ):
            raise HTTPException(
                status_code=400,
                detail="尚未生成最终方案，暂不能整理为框架卡片。",
            )

        card = await FrameworkBuilder(
            db=db,
            model_gateway=model_gateway,
        ).summarize_to_card(
            [
                {"role": item.role, "content": item.content}
                for item in messages
                if item.role in {"user", "assistant"}
            ]
        )
        title = card.title_suggestion
        if title == "待补充":
            title = "论文框架卡片"
        artifact = ArtifactRepository(db).create_artifact(
            project_id=payload.project_id,
            artifact_type="framework_card",
            title=title[:300],
            content=card.to_dict(),
            markdown=render_framework_card_markdown(card),
        )
        db.commit()
        return ArtifactResponse.from_model(artifact)


@router.post("/topic/card", response_model=ArtifactResponse)
async def create_topic_guidance_card(
    payload: TopicGuidanceCardRequest,
    request: Request,
):
    model_gateway = request.app.state.model_gateway
    privacy = request.app.state.privacy
    if model_gateway is None and not privacy["local_only"]:
        raise HTTPException(
            status_code=503,
            detail="整理选题卡片需要调用大模型，请先配置 API Key 后重启服务。",
        )
    if model_gateway is None:
        raise HTTPException(
            status_code=503,
            detail="当前没有可用的大模型，暂时无法整理选题卡片。",
        )

    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        session_and_messages = repository.get_session_with_messages(
            payload.session_id,
        )
        if session_and_messages is None:
            raise HTTPException(status_code=404, detail="session not found")
        session, messages = session_and_messages
        if session.project_id != payload.project_id:
            raise HTTPException(status_code=404, detail="session not found")

        topic_replies = [
            message
            for message in messages
            if message.role == "assistant"
            and message.mode == ChatMode.TOPIC_GUIDANCE.value
        ]
        if not topic_replies or not is_topic_guidance_final_plan(
            topic_replies[-1].content,
        ):
            raise HTTPException(
                status_code=400,
                detail="尚未生成最终选题方案，暂不能整理为选题卡片。",
            )

        markdown = await TopicGuidanceService(
            db=db,
            model_gateway=model_gateway,
        ).summarize_to_markdown(
            [
                {"role": item.role, "content": item.content}
                for item in messages
                if item.role in {"user", "assistant"}
            ]
        )
        # Extract title from first heading in markdown
        import re as _re
        m = _re.search(r"^#+\s*(.+)$", markdown, _re.MULTILINE)
        title = (m.group(1).strip() or "选题方案卡片")[:300]
        artifact = ArtifactRepository(db).create_artifact(
            project_id=payload.project_id,
            artifact_type="topic_guidance_plan",
            title=title,
            content={"markdown": markdown},
            markdown=markdown,
        )
        db.commit()
        return ArtifactResponse.from_model(artifact)
