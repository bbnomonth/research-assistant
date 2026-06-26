"""LLM-powered intent classifier that routes user messages to the appropriate workflow.

Classifies into five categories:
- literature_discovery: search/retrieve/discover/recommend academic papers
- paper_reading: read/understand/summarize/analyze a specific paper
- topic_guidance: help student find a research topic, pick a thesis title, decide research direction
- framework_building: help student build a thesis framework from an existing topic via Socratic questioning
- other: general Q&A with no preset prompts — direct native model call
"""

import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from research_agent.schemas.chat import ChatMode
from research_agent.services.model_gateway import ModelGateway


_KEYWORDS: Dict[ChatMode, List[str]] = {
    ChatMode.LITERATURE_DISCOVERY: [
        "搜索", "检索", "文献推荐", "找文献", "arxiv",
        "最新论文", "论文检索", "查找论文", "paper search",
        "帮我找", "有什么相关", "推荐一些", "检索",
    ],
    ChatMode.PAPER_READING: [
        "pdf", "精读", "这篇文章", "这篇论文", "上传的",
        "paper reading", "阅读", "帮我读", "这篇文章的",
    ],
    ChatMode.TOPIC_GUIDANCE: [
        "选题", "帮我定题", "研究方向", "研究主题", "想研究",
        "论文题目", "研究方向不明确", "不知道做什么", "想写论文",
        "研究计划", "如何选题", "选什么题", "定题",
        "诊断", "评估我的", "分析我的", "给点建议",
        "这个方向", "这个课题", "研究现状",
    ],
    ChatMode.FRAMEWORK_BUILDING: [
        "搭框架", "帮我搭框架", "搭建框架", "论文框架设计",
        "研究框架设计", "章节结构", "帮我梳理论文框架", "完善框架",
        "框架调整", "论文结构", "章节安排", "论文框架",
    ],
}


def classify_by_keywords(message: str) -> ChatMode:
    """Keyword-based fallback when the model is not available."""
    normalized = message.casefold()
    for mode, words in _KEYWORDS.items():
        if any(w.casefold() in normalized for w in words):
            return mode
    return ChatMode.OTHER


class IntentClassification(BaseModel):
    mode: ChatMode
    confidence: float = 0.0
    reasoning: str = ""


async def classify_intent(
    gateway: ModelGateway,
    content: str,
) -> IntentClassification:
    """Use the LLM to classify the user's intent into a ChatMode.

    Falls back to keyword matching on any error so the system
    never blocks on model availability.
    """
    prompt = (
        'You are a research assistant intent classifier.\n'
        "Given a user's message, classify the intent into one of five categories:\n"
        "1. literature_discovery - Any request to search, retrieve, discover, "
        "or recommend academic papers or research articles.\n"
        "2. paper_reading - Requests related to reading, understanding, "
        "summarizing, or analyzing a specific paper.\n"
        "3. topic_guidance - Requests for help finding, evaluating, or refining a research topic, "
        "picking a thesis title, deciding a research direction, or generating "
        "a research plan from scratch.\n"
        "4. framework_building - Requests for help building a structured thesis "
        "framework (chapter outline, core logic, research methods) from an "
        "existing topic or title using Socratic questioning.\n"
        "5. other - General questions, explanations, definitions, greetings, "
        "or anything not fitting the other four categories. "
        "This mode calls the native model with no preset system prompts.\n"
        "Return ONLY a JSON object with keys: mode, confidence, reasoning.\n"
        "mode must be one of: literature_discovery, paper_reading, topic_guidance, framework_building, other.\n"
        "confidence is a number between 0 and 1.\n"
        "reasoning is a brief explanation in Chinese.\n"
        "Examples:\n"
        '{"mode": "literature_discovery", "confidence": 0.95, "reasoning": "用户明确要求检索论文"}'
        "\n"
        '{"mode": "topic_guidance", "confidence": 0.92, "reasoning": "用户请求帮助确定研究方向和选题"}'
        "\n"
        '{"mode": "framework_building", "confidence": 0.90, "reasoning": "用户有明确选题，请求帮忙搭建论文框架和章节结构"}'
        "\n"
        '{"mode": "other", "confidence": 0.92, "reasoning": "用户询问什么是混合整数规划，属于一般知识问答"}'
        "\n"
        f"User message: {content[:1500]}"
    )

    try:
        parts = [
            token
            async for token in gateway.stream_chat(
                [{"role": "user", "content": prompt}]
            )
        ]
        response = "".join(parts).strip()

        json_str = _extract_json(response)
        parsed = IntentClassification.model_validate_json(json_str)
        return parsed
    except Exception:
        return IntentClassification(
            mode=classify_by_keywords(content),
            confidence=0.0,
            reasoning="Model unavailable, using keyword fallback",
        )


def _extract_json(text: str) -> str:
    """Extract JSON object from LLM response text."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text
