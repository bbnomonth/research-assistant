import time
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from research_agent.db.models import ModelCallLog
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.chat import ChatMode, StreamEvent
from research_agent.services.arxiv_search import ArxivSearchProvider
from research_agent.services.guided_reading import GuidedReadingService
from research_agent.services.literature import (
    LiteratureDiscoveryService,
    LocalLiteratureDiscoveryService,
)
from research_agent.services.model_gateway import (
    ModelGateway,
    build_qwen_messages,
)
from research_agent.services.research_diagnosis import ResearchDiagnosisService
from research_agent.services.intent_classifier import (
    classify_by_keywords,
    classify_intent,
)


def derive_session_title(content: str, max_length: int = 24) -> str:
    """Simple prefix-based title when model is unavailable."""
    cleaned = content.strip().replace("\n", " ").replace("\r", " ")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return "新会话"
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


async def generate_session_title_from_model(
    gateway: "ModelGateway",
    content: str,
) -> str:
    """Use the LLM to extract a concise semantic title from the first message."""
    prompt = (
        "Given the following research question or statement, generate a concise Chinese title "
        "for this conversation session. The title should be 8-15 Chinese characters, "
        "accurately reflecting the core topic. Return ONLY the title text, no quotes, no explanation.\n\n"
        f"User message: {content[:500]}"
    )
    try:
        parts = [
            token
            async for token in gateway.stream_chat(
                [{"role": "user", "content": prompt}]
            )
        ]
        title = "".join(parts).strip()
        title = title.strip("\"'，。、：；！？「」『』（）[]{}")
        if not title or len(title) < 3:
            return derive_session_title(content)
        if len(title) > 20:
            title = title[:19].rstrip() + "…"
        return title
    except Exception:
        return derive_session_title(content)


class ConversationService:
    def __init__(
        self,
        db: Session,
        model_gateway: Optional[ModelGateway],
        arxiv_provider: Optional[ArxivSearchProvider] = None,
    ) -> None:
        self.db = db
        self.model_gateway = model_gateway
        self.arxiv_provider = arxiv_provider
        self.repository = ConversationRepository(db)

    async def _classify_mode(
        self,
        content: str,
        mode_override: Optional[ChatMode],
    ) -> ChatMode:
        """Classify the user's intent using LLM when available, else keyword fallback."""
        if mode_override is not None:
            return mode_override
        if self.model_gateway is not None:
            classification = await classify_intent(self.model_gateway, content)
            return classification.mode
        return classify_by_keywords(content)

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

        existing_messages = self.repository.list_messages(conversation.id)
        is_first_user_message = not any(
            message.role == "user" for message in existing_messages
        )
        self.repository.add_message(conversation.id, "user", content)

        if is_first_user_message and not conversation.title:
            if self.model_gateway is not None:
                conversation.title = await generate_session_title_from_model(
                    self.model_gateway,
                    content,
                )
            else:
                conversation.title = derive_session_title(content)

        self.repository.touch_session(conversation.id)
        self.db.commit()

        mode = await self._classify_mode(content, mode_override)

        yield StreamEvent(event="mode", data={"mode": mode.value})
        yield StreamEvent(
            event="metadata",
            data={
                "project_id": project.id,
                "session_id": conversation.id,
                "title": conversation.title or derive_session_title(content),
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
                            "论文检索服务暂时不可用，请稍后重试；"
                            "普通问答和本地论文功能不受影响。"
                        )
                    },
            )
            return

        if mode is ChatMode.RESEARCH_DIAGNOSIS:
            if self.model_gateway is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "研究诊断需要调用大模型，请先在后台配置 API Key 后重启服务。"
                        ),
                        "code": "MODEL_NOT_CONFIGURED",
                    },
                )
                return
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
                            "请先在「论文与证据」页面选择或上传一篇论文，"
                            "再使用引导式精读功能。"
                        ),
                        "code": "PAPER_READING_REQUIRES_PAPER",
                    },
                )
                return
            if self.model_gateway is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "引导式精读需要调用大模型，请先在后台配置 API Key 后重启服务。"
                        ),
                        "code": "MODEL_NOT_CONFIGURED",
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
                error_msg = str(exc)
                if "no parsed evidence" in error_msg.lower():
                    yield StreamEvent(
                        event="error",
                        data={
                            "message": (
                                "该论文尚未完成解析，暂时无法进行引导式精读。"
                                "请在「论文与证据」页面确认该论文状态为「已完成」。"
                            ),
                            "code": "PAPER_NOT_PARSED",
                        },
                    )
                else:
                    yield StreamEvent(
                        event="error",
                        data={"message": error_msg, "code": "GUIDED_READING_ERROR"},
                    )
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "引导式精读暂时不可用，请稍后重试；"
                            "已保存的论文和阅读记录不会受到影响。"
                        ),
                        "code": "GUIDED_READING_ERROR",
                    },
                )
            return

        if self.model_gateway is None:
            yield StreamEvent(
                event="error",
                data={
                    "message": (
                        "模型暂不可用，请检查后台配置后重启服务。"
                    )
                },
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
            data={"name": "query_generation", "label": "生成检索式"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "arxiv_search", "label": "检索论文数据库"},
        )
        if self.model_gateway is None:
            service = LocalLiteratureDiscoveryService(self.arxiv_provider)
            result = await service.discover(content)
            artifact = None
        else:
            svc = LiteratureDiscoveryService(
                model_gateway=self.model_gateway,
                arxiv_provider=self.arxiv_provider,
                db=self.db,
                project_id=project_id,
            )
            result, artifact = await svc.discover_with_artifact(content)
        yield StreamEvent(
            event="stage",
            data={"name": "recommendation", "label": "生成推荐卡片"},
        )
        yield StreamEvent(
            event="stage",
            data={"name": "persistence", "label": "保存到研究项目"},
        )
        PaperRepository(self.db).upsert_arxiv_papers(
            project_id,
            result.recommendations,
        )
        rec_count = len(result.recommendations)
        summary = (
            f"已根据你的问题检索了论文数据库，"
            f"从 {len(result.candidates)} 篇候选中筛选出 {rec_count} 篇推荐文献。"
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
        if artifact is not None:
            yield StreamEvent(
                event="artifact",
                data={
                    "artifact_id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "title": artifact.title,
                    "evidence_pages": [],
                },
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
