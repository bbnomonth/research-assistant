import time
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from research_agent.db.models import ModelCallLog
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.chat import ChatMode, StreamEvent
from research_agent.services.arxiv_search import ArxivSearchProvider
from research_agent.services.guided_reading import GuidedReadingService
from research_agent.services.literature import LiteratureDiscoveryService
from research_agent.services.model_gateway import (
    ModelGateway,
    build_qwen_messages,
)
from research_agent.services.research_diagnosis import ResearchDiagnosisService
from research_agent.workflows.router import build_router_graph


PENDING_WORKFLOW_MESSAGE = (
    "该模式已经完成路由与数据结构设计，将在后续阶段接入具体工作流。"
)


class ConversationService:
    def __init__(
        self,
        db: Session,
        model_gateway: ModelGateway,
        arxiv_provider: Optional[ArxivSearchProvider] = None,
    ) -> None:
        self.db = db
        self.model_gateway = model_gateway
        self.arxiv_provider = arxiv_provider
        self.repository = ConversationRepository(db)
        self.router_graph = build_router_graph()

    async def stream_reply(
        self,
        content: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        paper_id: Optional[str] = None,
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

        if (
            mode is ChatMode.LITERATURE_DISCOVERY
            and self.arxiv_provider is not None
        ):
            try:
                async for event in self._stream_literature_discovery(
                    project.id,
                    conversation.id,
                    content,
                ):
                    yield event
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "arXiv 文献检索暂时不可用，请稍后重试；"
                            "普通问答和本地论文功能不受影响。"
                        )
                    },
            )
            return

        if mode is ChatMode.RESEARCH_DIAGNOSIS:
            try:
                async for event in self._stream_research_diagnosis(
                    project.id,
                    conversation.id,
                    content,
                ):
                    yield event
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "研究诊断暂时不可用，请稍后重试；"
                            "已保存的项目和文献不会受影响。"
                        )
                    },
                )
            return

        if mode is ChatMode.PAPER_READING:
            if paper_id is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "引导式精读需要显式提供 paper_id，系统不会自动猜测论文。"
                        )
                    },
                )
                return
            try:
                async for event in self._stream_guided_reading(
                    project.id,
                    conversation.id,
                    paper_id,
                    content,
                    history,
                ):
                    yield event
            except (LookupError, ValueError) as exc:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={"message": str(exc)},
                )
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "引导式精读暂时不可用，请稍后重试；"
                            "已保存的论文和阅读记录不会受到影响。"
                        )
                    },
                )
            return

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

    async def _stream_literature_discovery(
        self,
        project_id: str,
        session_id: str,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event="stage",
            data={"name": "query_generation", "label": "生成英文检索式"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "arxiv_search", "label": "检索 arXiv"},
        )
        service = LiteratureDiscoveryService(
            model_gateway=self.model_gateway,
            arxiv_provider=self.arxiv_provider,
            db=self.db,
        )
        result = await service.discover(content)
        yield StreamEvent(
            event="stage",
            data={"name": "recommendation", "label": "筛选推荐文献"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "persistence", "label": "保存到研究项目"},
        )
        PaperRepository(self.db).upsert_arxiv_papers(
            project_id,
            result.recommendations,
        )
        summary = (
            f"已使用检索式 `{result.query}` 检索 arXiv，"
            f"从 {len(result.candidates)} 篇候选中推荐"
            f" {len(result.recommendations)} 篇文献。"
        )
        self.repository.add_message(
            session_id,
            "assistant",
            summary,
            mode=ChatMode.LITERATURE_DISCOVERY.value,
        )
        self.db.commit()
        yield StreamEvent(
            event="search_results",
            data=result.model_dump(),
        )
        yield StreamEvent(event="token", data={"content": summary})
        yield StreamEvent(event="done", data={"content": summary})

    async def _stream_research_diagnosis(
        self,
        project_id: str,
        session_id: str,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event="stage",
            data={"name": "evidence_collection", "label": "收集项目文献证据"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "diagnosis", "label": "生成研究诊断"},
        )
        result = await ResearchDiagnosisService(
            db=self.db,
            model_gateway=self.model_gateway,
        ).diagnose(project_id, content)
        yield StreamEvent(
            event="stage",
            data={"name": "persistence", "label": "保存诊断成果"},
        )
        summary = (
            "已根据当前项目材料生成研究诊断，并保存为可编辑成果。"
        )
        self.repository.add_message(
            session_id,
            "assistant",
            summary,
            mode=ChatMode.RESEARCH_DIAGNOSIS.value,
        )
        self.db.commit()
        yield StreamEvent(
            event="artifact",
            data={
                "artifact_id": result.artifact.id,
                "artifact_type": result.artifact.artifact_type,
                "title": result.artifact.title,
                "evidence_pages": result.evidence_pages,
            },
        )
        yield StreamEvent(event="token", data={"content": summary})
        yield StreamEvent(event="done", data={"content": summary})

    async def _stream_guided_reading(
        self,
        project_id: str,
        session_id: str,
        paper_id: str,
        content: str,
        history,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event="stage",
            data={"name": "evidence_collection", "label": "收集论文证据"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "reading_guidance", "label": "生成阅读反馈"},
        )
        result = await GuidedReadingService(
            db=self.db,
            model_gateway=self.model_gateway,
        ).guide(
            project_id=project_id,
            paper_id=paper_id,
            user_input=content,
            history=[
                {"role": item.role, "content": item.content}
                for item in history
            ],
        )
        response = result.turn.feedback
        if result.turn.next_question:
            response = f"{response}\n\n{result.turn.next_question}".strip()
        self.repository.add_message(
            session_id,
            "assistant",
            response,
            mode=ChatMode.PAPER_READING.value,
        )
        self.db.commit()
        yield StreamEvent(
            event="evidence",
            data={"paper_id": paper_id, "pages": result.evidence_pages},
        )
        if result.artifact is not None:
            yield StreamEvent(
                event="artifact",
                data={
                    "artifact_id": result.artifact.id,
                    "artifact_type": result.artifact.artifact_type,
                    "title": result.artifact.title,
                    "evidence_pages": result.evidence_pages,
                },
            )
        yield StreamEvent(event="token", data={"content": response})
        yield StreamEvent(event="done", data={"content": response})
