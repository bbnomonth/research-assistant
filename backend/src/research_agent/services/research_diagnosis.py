import time
from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway, collect_chat


# ── 框架搭建导师：单 LLM 系统提示词 ──────────────────────────────────────────────

_FRAMEWORK_BUILDING_SYSTEM = """你是一名水平极其高超且严谨的研究生论文框架搭建导师。你将以苏格拉底提问法帮助我搭建论文框架。我已有一个选题或导师提供的大致研究方向，但还需要进一步明确研究问题、核心概念、理论基础、研究思路与章节结构。
请不要一开始直接给出完整框架，而是每次只提出1个最关键的问题，引导我逐步澄清包括但不限于：研究对象、研究问题、核心变量/概念、研究价值、文献基础、方法选择与可能创新点。
你的问题应简洁、具体、有推进性。根据我的回答继续追问、归纳或校正方向。只有当你对论文框架已有95%以上信心时，才输出最终方案。
最终方案应包括：题目优化建议、研究问题、核心论证逻辑、章节结构、每章写作重点、可能的研究方法与创新点。"""


@dataclass(frozen=True)
class FrameworkChatResult:
    """Outcome of one turn of free-form framework building chat."""

    assistant_message: str


class FrameworkBuilder:
    """Socratic framework-building chat engine.

    One LLM call per turn with a single system prompt.
    """

    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.gateway = model_gateway

    async def chat(
        self,
        history: List[dict],
        user_input: str,
    ) -> FrameworkChatResult:
        """One turn of free-form framework-building dialogue.

        `history` should be the conversation so far in OpenAI message format,
        excluding the current user message. The current `user_input` is
        appended automatically.
        """
        messages = [
            {"role": "system", "content": _FRAMEWORK_BUILDING_SYSTEM},
            *history,
            {"role": "user", "content": user_input},
        ]

        started = time.perf_counter()
        try:
            response = await collect_chat(self.gateway, messages)
        except Exception as exc:
            record_model_call(
                self.db,
                "framework_building_chat",
                self.gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

        record_model_call(
            self.db,
            "framework_building_chat",
            self.gateway.model_name,
            started,
            0,
            True,
        )
        return FrameworkChatResult(assistant_message=response.strip())
