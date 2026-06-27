import time
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from research_agent.db.models import ModelCallLog, Paper
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.chat import ChatMode, StreamEvent
from research_agent.schemas.literature import LiteratureDiscoveryResult, RecommendedPaper
from research_agent.services.arxiv_search import ArxivSearchProvider
from research_agent.services.guided_reading import GuidedReadingService
from research_agent.services.literature import (
    LiteratureDiscoveryService,
    LocalLiteratureDiscoveryService,
)
from research_agent.services.model_gateway import (
    ModelGateway,
    build_qwen_messages,
    collect_chat,
)
from research_agent.services.topic_guidance import (
    TopicGuidanceService,
    is_topic_guidance_final_plan,
)
from research_agent.services.framework_building import (
    FrameworkBuilder,
    is_framework_final_plan,
)
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


SESSION_TITLE_SYSTEM_PROMPT = """你是一个研究辅助系统的会话标题生成器。你的任务是根据用户的第一条有效输入，为当前会话生成一个简洁、准确的中文标题。

要求：
1. 标题应概括用户的核心任务或研究主题。
2. 标题长度控制在 6 到 18 个汉字之间。
3. 不要使用“关于”“讨论”“问题”等空泛词开头。
4. 不要添加标点符号。
5. 不要输出解释、推理过程、编号或 JSON。
6. 如果用户输入是文献检索需求，标题应体现检索主题。
7. 如果用户输入是论文框架或选题需求，标题应体现研究方向。
8. 如果用户输入过短或含义不明确，生成一个保守标题，例如“自由问答”。

请只输出最终标题。"""


async def generate_session_title(
    gateway: Optional[ModelGateway],
    content: str,
) -> str:
    """Generate a concise session title with the fast model, falling back locally."""
    fallback = derive_session_title(content)
    if gateway is None:
        return fallback
    try:
        title = await collect_chat(
            gateway,
            [
                {"role": "system", "content": SESSION_TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": content[:1500]},
            ],
        )
    except Exception:
        return fallback
    cleaned = _clean_generated_title(title)
    return cleaned or fallback


def _clean_generated_title(title: str) -> str:
    cleaned = title.strip().strip("` \n\r\t。！？；;，,：:")
    cleaned = " ".join(cleaned.split())
    for prefix in ("标题：", "会话标题：", "最终标题："):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned[:24].strip()


def _unique_evidence_pages(evidence) -> list[int]:
    pages = []
    for item in evidence:
        if item.page_number not in pages:
            pages.append(item.page_number)
    return pages


def _papers_to_cache(result: LiteratureDiscoveryResult) -> list[RecommendedPaper]:
    by_id = {item.paper.arxiv_id: item for item in result.recommendations}
    cached: list[RecommendedPaper] = list(result.recommendations)
    for paper in result.candidates:
        if paper.arxiv_id in by_id:
            continue
        cached.append(
            RecommendedPaper(
                paper=paper,
                reason="该文献与当前检索主题相关，建议进一步查看原文并核对方法、场景和结论。",
                purpose_labels=["候选文献"],
            )
        )
    return cached


class ConversationService:
    def __init__(
        self,
        db: Session,
        model_gateway: Optional[ModelGateway],
        router_gateway: Optional[ModelGateway] = None,
        arxiv_provider: Optional[ArxivSearchProvider] = None,
    ) -> None:
        self.db = db
        self.model_gateway = model_gateway
        self.router_gateway = router_gateway or model_gateway
        self.arxiv_provider = arxiv_provider
        self.repository = ConversationRepository(db)

    async def _classify_mode(
        self,
        content: str,
        mode_override: Optional[ChatMode],
        history=None,
    ) -> ChatMode:
        """Classify the user's intent using LLM when available, else keyword fallback."""
        if mode_override is not None:
            return mode_override
        inherited = self._inherited_mode(history or [])
        if inherited is not None:
            return inherited
        if self.router_gateway is not None:
            classification = await classify_intent(self.router_gateway, content)
            return classification.mode
        return classify_by_keywords(content)

    @staticmethod
    def _inherited_mode(history) -> Optional[ChatMode]:
        sticky_modes = {
            ChatMode.FRAMEWORK_BUILDING,
            ChatMode.TOPIC_GUIDANCE,
            ChatMode.PAPER_READING,
        }
        for message in reversed(history):
            if message.role != "assistant" or not message.mode:
                continue
            try:
                mode = ChatMode(message.mode)
            except ValueError:
                return None
            return mode if mode in sticky_modes else None
        return None

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
        self.repository.add_message(
            conversation.id,
            "user",
            content,
            metadata=self._paper_message_metadata(paper_id),
        )

        if is_first_user_message and not conversation.title:
            conversation.title = await generate_session_title(
                self.router_gateway,
                content,
            )

        self.repository.touch_session(conversation.id)
        self.db.commit()

        mode = await self._classify_mode(content, mode_override, history)

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

        if mode is ChatMode.PAPER_READING:
            if paper_id is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "请先在「论文库」页面选择或上传一篇论文，"
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
                                "请在「论文库」页面确认该论文状态为「已完成」。"
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

        if mode is ChatMode.TOPIC_GUIDANCE:
            if self.model_gateway is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "选题导师需要调用大模型，请先在后台配置 API Key 后重启服务。"
                        ),
                        "code": "MODEL_NOT_CONFIGURED",
                    },
                )
                return
            try:
                async for event in self._stream_topic_guidance(
                    project.id,
                    conversation.id,
                    content,
                    history,
                ):
                    yield event
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "选题导师暂时不可用，请稍后重试。"
                        )
                    },
                )
                return
            return

        if mode is ChatMode.FRAMEWORK_BUILDING:
            if self.model_gateway is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "搭框架需要调用大模型，请先在后台配置 API Key 后重启服务。"
                        ),
                        "code": "MODEL_NOT_CONFIGURED",
                    },
                )
                return
            try:
                async for event in self._stream_framework_building(
                    project.id,
                    conversation.id,
                    content,
                    history,
                ):
                    yield event
            except Exception:
                self.db.rollback()
                yield StreamEvent(
                    event="error",
                    data={
                        "message": (
                            "搭框架暂时不可用，请稍后重试。"
                        )
                    },
                )
                return
            return

        if mode is ChatMode.OTHER:
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

            started = time.perf_counter()
            pieces = []
            native_messages = [
                {"role": "user", "content": content}
            ]
            try:
                async for token in self.model_gateway.stream_chat(native_messages):
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
            return

        if self.model_gateway is None:
            yield StreamEvent(
                event="error",
                data={
                    "message": (
                        "该功能需要调用大模型，请先在后台配置 API Key 后重启服务。"
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
            data={"name": "persistence", "label": "缓存检索结果"},
        )
        PaperRepository(self.db).upsert_arxiv_papers(
            project_id,
            _papers_to_cache(result),
        )
        rec_count = len(result.recommendations)
        summary = (
            f"已根据你的问题检索了论文数据库，"
            f"从 {len(result.candidates)} 篇候选中筛选出 {rec_count} 篇推荐文献。"
            "收藏后才会进入论文库，并可用于导入、精读和对比。"
        )
        self.repository.add_message(
            session_id,
            "assistant",
            summary,
            mode=ChatMode.LITERATURE_DISCOVERY.value,
            metadata={"search_results": result.model_dump()},
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
        result = None
        async for event in GuidedReadingService(
            db=self.db,
            model_gateway=self.model_gateway,
        ).stream_guide(
            project_id=project_id,
            paper_id=paper_id,
            user_input=content,
            history=[
                {"role": item.role, "content": item.content}
                for item in history
            ],
        ):
            if event["type"] == "token":
                yield StreamEvent(event="token", data={"content": event["content"]})
            elif event["type"] == "done":
                result = event

        if result is None:
            yield StreamEvent(
                event="error",
                data={"message": "引导式精读未生成有效回复。"},
            )
            return
        turn = result["turn"]
        evidence = result["evidence"]
        artifact = result["artifact"]
        response = turn.feedback
        if turn.next_question:
            response = f"{response}\n\n{turn.next_question}".strip()
        self.repository.add_message(
            session_id,
            "assistant",
            response,
            mode=ChatMode.PAPER_READING.value,
            metadata=self._paper_message_metadata(paper_id),
        )
        self.db.commit()
        yield StreamEvent(
            event="evidence",
            data={
                "paper_id": paper_id,
                "pages": _unique_evidence_pages(evidence),
            },
        )
        if artifact is not None:
            yield StreamEvent(
                event="artifact",
                data={
                    "artifact_id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "title": artifact.title,
                    "evidence_pages": _unique_evidence_pages(evidence),
                },
            )
        yield StreamEvent(event="done", data={"content": response})
        if turn.completed:
            yield StreamEvent(
                event="guided_reading_card_offer",
                data={
                    "project_id": project_id,
                    "session_id": session_id,
                    "paper_id": paper_id,
                    "title": "整理为精读卡片",
                },
            )

    def _paper_message_metadata(self, paper_id: Optional[str]) -> dict:
        if not paper_id:
            return {}
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            return {"paper_id": paper_id}
        return {
            "paper_id": paper.id,
            "paper_title": paper.title,
            "paper_arxiv_id": paper.arxiv_id,
        }

    async def _stream_topic_guidance(
        self,
        project_id: str,
        session_id: str,
        content: str,
        history,
    ) -> AsyncIterator[StreamEvent]:
        history_dicts = [
            {"role": item.role, "content": item.content}
            for item in history
        ]
        # Drop trailing duplicate user message (same logic as _stream_framework_building)
        while (
            history_dicts
            and history_dicts[-1].get("role") == "user"
            and history_dicts[-1].get("content") == content
        ):
            history_dicts.pop()

        svc = TopicGuidanceService(db=self.db, model_gateway=self.model_gateway)

        try:
            pieces = []
            async for token in svc.stream_guidance(
                history=history_dicts,
                user_input=content,
            ):
                pieces.append(token)
                yield StreamEvent(event="token", data={"content": token})
        except Exception:
            yield StreamEvent(
                event="error",
                data={"message": "选题导师暂时不可用，请稍后重试。"},
            )
            return

        assistant_text = "".join(pieces).strip()
        self.repository.add_message(
            session_id,
            "assistant",
            assistant_text,
            mode=ChatMode.TOPIC_GUIDANCE.value,
        )
        self.db.commit()

        if is_topic_guidance_final_plan(assistant_text):
            yield StreamEvent(
                event="topic_guidance_card_offer",
                data={
                    "project_id": project_id,
                    "session_id": session_id,
                    "title": "整理为选题卡片",
                },
            )
        yield StreamEvent(event="done", data={"content": assistant_text})

    async def _stream_framework_building(
        self,
        project_id: str,
        session_id: str,
        user_input: str,
        history,
    ) -> AsyncIterator[StreamEvent]:
        history_dicts = [
            {"role": item.role, "content": item.content}
            for item in history
        ]
        # `history_dicts` may already include the current turn's user message
        # (the route persists it before calling us). Drop the trailing
        # duplicate so the LLM sees it exactly once.
        while (
            history_dicts
            and history_dicts[-1].get("role") == "user"
            and history_dicts[-1].get("content") == user_input
        ):
            history_dicts.pop()

        svc = FrameworkBuilder(db=self.db, model_gateway=self.model_gateway)

        try:
            pieces = []
            async for token in svc.stream_chat(
                history=history_dicts,
                user_input=user_input,
            ):
                pieces.append(token)
                yield StreamEvent(event="token", data={"content": token})
        except Exception:
            yield StreamEvent(
                event="error",
                data={"message": "搭框架服务暂时不可用，请稍后重试。"},
            )
            return

        assistant_text = "".join(pieces).strip()
        self.repository.add_message(
            session_id,
            "assistant",
            assistant_text,
            mode=ChatMode.FRAMEWORK_BUILDING.value,
        )
        self.db.commit()
        if is_framework_final_plan(assistant_text):
            yield StreamEvent(
                event="framework_card_offer",
                data={
                    "project_id": project_id,
                    "session_id": session_id,
                    "title": "整理为框架卡片",
                },
            )
        yield StreamEvent(event="done", data={"content": assistant_text})
