import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, List

from sqlalchemy.orm import Session

from research_agent.schemas.system import FrameworkChapterOutline
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway, collect_chat


# ── 框架搭建导师：单 LLM 系统提示词 ──────────────────────────────────────────────

_FRAMEWORK_BUILDING_SYSTEM = """你是一名水平极其高超且严谨的研究生论文框架搭建导师。你将以苏格拉底提问法帮助我搭建论文框架。我已有一个选题或导师提供的大致研究方向，但还需要进一步明确研究问题、核心概念、理论基础、研究思路与章节结构。
请不要一开始直接给出完整框架，而是每次只提出1个最关键的问题，引导我逐步澄清包括但不限于：研究对象、研究问题、核心变量/概念、研究价值、文献基础、方法选择与可能创新点。
你的问题应简洁、具体、有推进性。根据我的回答继续追问、归纳或校正方向。只有当你对论文框架已有95%以上信心时，才输出最终方案。
最终方案应包括：题目优化建议、研究问题、核心论证逻辑、章节结构、每章写作重点、可能的研究方法与创新点。"""

_FRAMEWORK_CARD_SYSTEM = """你是一名学术成果整理助手。下面是一段研究生与论文框架搭建导师之间的对话。请只基于对话内容整理为一张结构化论文框架卡片，用于保存到研究项目成果。
只返回 JSON，不要任何额外说明。字段必须严格一致：
- title_suggestion: 字符串，题目优化建议
- research_questions: 字符串数组，核心研究问题
- core_logic: 字符串，核心论证逻辑
- chapter_structure: 对象数组，每项含 chapter、title、key_points
- research_methods: 字符串数组，可能研究方法
- innovations: 字符串数组，可能创新点
- priority_concepts_methods: 字符串数组，完成这篇论文前应优先了解的核心概念、理论工具、算法方法、评价指标或数据处理方法；每一项用一句话说明为什么需要掌握。该字段应基于本次对话中的选题、研究问题、方法路线和应用场景生成，避免泛泛而谈，优先给出与当前论文方向直接相关的内容。
- dialogue_summary: 字符串，对话总结（2-4句话）
信息不足处写“待补充”，不要编造。"""

_FINAL_PLAN_MARKERS = (
    "最终方案",
    "题目优化",
    "研究问题",
    "核心论证逻辑",
    "章节结构",
    "每章写作重点",
    "研究方法",
    "创新点",
)


def is_framework_final_plan(text: str) -> bool:
    """Return true only when the assistant appears to have produced the final plan."""
    normalized = text.strip()
    if len(normalized) < 120:
        return False
    marker_hits = sum(1 for marker in _FINAL_PLAN_MARKERS if marker in normalized)
    chapter_hits = sum(1 for marker in ("第一章", "第二章", "第三章") if marker in normalized)
    return marker_hits >= 4 or (marker_hits >= 3 and chapter_hits >= 2)


@dataclass(frozen=True)
class FrameworkChatResult:
    """Outcome of one turn of free-form framework building chat."""

    assistant_message: str


@dataclass(frozen=True)
class FrameworkCard:
    title_suggestion: str
    research_questions: List[str]
    core_logic: str
    chapter_structure: List[FrameworkChapterOutline]
    research_methods: List[str]
    innovations: List[str]
    priority_concepts_methods: List[str]
    dialogue_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_suggestion": self.title_suggestion,
            "research_questions": self.research_questions,
            "core_logic": self.core_logic,
            "chapter_structure": [
                item.model_dump() for item in self.chapter_structure
            ],
            "research_methods": self.research_methods,
            "innovations": self.innovations,
            "priority_concepts_methods": self.priority_concepts_methods,
            "dialogue_summary": self.dialogue_summary,
        }


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

    async def stream_chat(
        self,
        history: List[dict],
        user_input: str,
    ) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": _FRAMEWORK_BUILDING_SYSTEM},
            *history,
            {"role": "user", "content": user_input},
        ]

        started = time.perf_counter()
        try:
            async for token in self.gateway.stream_chat(messages):
                yield token
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

    async def summarize_to_card(
        self,
        messages: List[dict],
    ) -> FrameworkCard:
        transcript = _format_transcript(messages)
        prompt = f"对话内容：\n{transcript}"
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.gateway,
                [
                    {"role": "system", "content": _FRAMEWORK_CARD_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            record_model_call(
                self.db,
                "framework_card",
                self.gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

        record_model_call(
            self.db,
            "framework_card",
            self.gateway.model_name,
            started,
            0,
            True,
        )
        return _parse_framework_card(response)


def render_framework_card_markdown(card: FrameworkCard) -> str:
    chapters = "\n".join(
        f"- **{item.chapter or '章节'} {item.title or '待补充'}**：{item.key_points or '待补充'}"
        for item in card.chapter_structure
    ) or "- 待补充"
    questions = "\n".join(f"- {item}" for item in card.research_questions) or "- 待补充"
    methods = "\n".join(f"- {item}" for item in card.research_methods) or "- 待补充"
    innovations = "\n".join(f"- {item}" for item in card.innovations) or "- 待补充"
    priority_items = "\n".join(
        f"- {item}" for item in card.priority_concepts_methods
    ) or "- 待补充"
    return f"""# 论文框架卡片

## 题目优化建议
{card.title_suggestion or '待补充'}

## 研究问题
{questions}

## 核心论证逻辑
{card.core_logic or '待补充'}

## 章节结构
{chapters}

## 可能的研究方法
{methods}

## 可能的创新点
{innovations}

## 优先补足的概念与方法
{priority_items}

## 对话总结
{card.dialogue_summary or '待补充'}
"""


def _format_transcript(messages: List[dict]) -> str:
    lines = []
    for item in messages:
        role = item.get("role", "")
        if role == "system":
            continue
        label = "用户" if role == "user" else "框架搭建导师"
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{label}：{content}")
    return "\n\n".join(lines)[-12000:]


def _parse_framework_card(raw: str) -> FrameworkCard:
    payload = _load_json_object(raw)
    return FrameworkCard(
        title_suggestion=_as_text(payload.get("title_suggestion")),
        research_questions=_as_text_list(payload.get("research_questions")),
        core_logic=_as_text(payload.get("core_logic")),
        chapter_structure=[
            FrameworkChapterOutline(
                chapter=_as_text(item.get("chapter")),
                title=_as_text(item.get("title")),
                key_points=_as_text(item.get("key_points")),
            )
            for item in payload.get("chapter_structure", [])
            if isinstance(item, dict)
        ],
        research_methods=_as_text_list(payload.get("research_methods")),
        innovations=_as_text_list(payload.get("innovations")),
        priority_concepts_methods=_as_text_list(
            payload.get("priority_concepts_methods")
        ),
        dialogue_summary=_as_text(payload.get("dialogue_summary")),
    )


def _load_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("framework card output is not valid JSON")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("framework card output must be a JSON object")
    return parsed


def _as_text(value: Any) -> str:
    if value is None:
        return "待补充"
    text = str(value).strip()
    return text or "待补充"


def _as_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        items = [_as_text(item) for item in value]
        return [item for item in items if item]
    text = _as_text(value)
    return [] if text == "待补充" else [text]
