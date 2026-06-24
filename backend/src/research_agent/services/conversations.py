import time
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from research_agent.db.models import ModelCallLog
from research_agent.repositories.conversations import ConversationRepository
from research_agent.schemas.chat import ChatMode, StreamEvent
from research_agent.services.model_gateway import (
    ModelGateway,
    build_qwen_messages,
)
from research_agent.workflows.router import build_router_graph


PENDING_WORKFLOW_MESSAGE = (
    "该模式已经完成路由与数据结构设计，将在后续阶段接入具体工作流。"
)


class ConversationService:
    def __init__(
        self,
        db: Session,
        model_gateway: ModelGateway,
    ) -> None:
        self.db = db
        self.model_gateway = model_gateway
        self.repository = ConversationRepository(db)
        self.router_graph = build_router_graph()

    async def stream_reply(
        self,
        content: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        mode_override: Optional[ChatMode] = None,
    ) -> AsyncIterator[StreamEvent]:
        project, conversation = self.repository.ensure_conversation(
            project_id,
            session_id,
        )
        history = self.repository.list_recent_messages(conversation.id, 20)
        self.repository.add_message(conversation.id, "user", content)
        self.db.commit()

        state = self.router_graph.invoke(
            {
                "content": content,
                "mode_override": mode_override,
            }
        )
        mode = state["mode"]

        yield StreamEvent(event="mode", data={"mode": mode.value})
        yield StreamEvent(
            event="metadata",
            data={
                "project_id": project.id,
                "session_id": conversation.id,
            },
        )

        if mode is not ChatMode.GENERAL_QA:
            self.repository.add_message(
                conversation.id,
                "assistant",
                PENDING_WORKFLOW_MESSAGE,
                mode=mode.value,
            )
            self.db.commit()
            yield StreamEvent(
                event="token",
                data={"content": PENDING_WORKFLOW_MESSAGE},
            )
            yield StreamEvent(
                event="done",
                data={"content": PENDING_WORKFLOW_MESSAGE},
            )
            return

        model_messages = build_qwen_messages(
            [
                {"role": item.role, "content": item.content}
                for item in history
            ],
            content,
        )
        started = time.perf_counter()
        pieces = []
        try:
            async for token in self.model_gateway.stream_chat(model_messages):
                pieces.append(token)
                yield StreamEvent(event="token", data={"content": token})

            final_content = "".join(pieces)
            self.repository.add_message(
                conversation.id,
                "assistant",
                final_content,
                mode=mode.value,
            )
            self.db.add(
                ModelCallLog(
                    task_type=mode.value,
                    model=self.model_gateway.model_name,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    retries=0,
                    success=1,
                )
            )
            self.db.commit()
            yield StreamEvent(
                event="done",
                data={"content": final_content},
            )
        except Exception as exc:
            self.db.rollback()
            self.db.add(
                ModelCallLog(
                    task_type=mode.value,
                    model=self.model_gateway.model_name,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    retries=1,
                    success=0,
                    error_type=type(exc).__name__,
                )
            )
            self.db.commit()
            yield StreamEvent(
                event="error",
                data={
                    "message": "模型服务暂时不可用，请检查本地配置或稍后重试。"
                },
            )
