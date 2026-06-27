"""LLM-powered intent classifier that routes user messages to workflows."""

from typing import Dict, List, Optional

from pydantic import BaseModel

from research_agent.schemas.chat import ChatMode
from research_agent.services.model_gateway import ModelGateway


INTENT_CLASSIFIER_SYSTEM_PROMPT = """你是一个研究辅助系统的意图分类器。你的任务是根据用户最新输入，判断用户当前最需要进入哪一种工作模式。

可选模式只有以下六种：
空闲
选题指导
框架搭建
文献检索
文献解读
自由问答

分类规则：
1. 如果用户想确定研究方向、缩小题目、判断选题是否可行、寻找研究问题，输出：选题指导
2. 如果用户已有大致题目或方向，想搭建论文框架、章节结构、研究思路、研究问题链条，输出：框架搭建
3. 如果用户想搜索、查找、推荐、筛选、下载论文或文献，输出：文献检索
4. 如果用户想精读、解读、追问、分析某篇已选论文，输出：文献解读
5. 如果用户只是一般聊天、解释概念、问工具用法、问项目功能、问技术实现，输出：自由问答
6. 只有当用户没有提出任何明确任务时，才输出：空闲

请只输出一个模式名称，不要解释，不要输出推理过程，不要输出 JSON。"""


_LABEL_TO_MODE = {
    "空闲": ChatMode.OTHER,
    "选题指导": ChatMode.TOPIC_GUIDANCE,
    "框架搭建": ChatMode.FRAMEWORK_BUILDING,
    "文献检索": ChatMode.LITERATURE_DISCOVERY,
    "文献解读": ChatMode.PAPER_READING,
    "自由问答": ChatMode.OTHER,
    "topic_guidance": ChatMode.TOPIC_GUIDANCE,
    "framework_building": ChatMode.FRAMEWORK_BUILDING,
    "literature_discovery": ChatMode.LITERATURE_DISCOVERY,
    "paper_reading": ChatMode.PAPER_READING,
    "other": ChatMode.OTHER,
}

_KEYWORDS: Dict[ChatMode, List[str]] = {
    ChatMode.LITERATURE_DISCOVERY: [
        "搜索",
        "检索",
        "文献推荐",
        "找文献",
        "arxiv",
        "最新论文",
        "论文检索",
        "查找论文",
        "paper search",
        "帮我找",
        "相关论文",
        "推荐一些",
    ],
    ChatMode.PAPER_READING: [
        "pdf",
        "精读",
        "这篇文章",
        "这篇论文",
        "上传的",
        "paper reading",
        "阅读",
        "帮我读",
        "解读",
        "原文",
    ],
    ChatMode.TOPIC_GUIDANCE: [
        "选题",
        "帮我定题",
        "研究方向",
        "研究主题",
        "想研究",
        "论文题目",
        "研究方向不明确",
        "不知道做什么",
        "想写论文",
        "研究计划",
        "如何选题",
        "选什么题",
        "定题",
        "诊断",
        "评估我的",
        "分析我的",
        "给点建议",
        "这个方向",
        "这个课题",
        "研究现状",
    ],
    ChatMode.FRAMEWORK_BUILDING: [
        "搭框架",
        "帮我搭框架",
        "搭建框架",
        "论文框架设计",
        "研究框架设计",
        "章节结构",
        "帮我梳理论文框架",
        "完善框架",
        "框架调整",
        "论文结构",
        "章节安排",
        "论文框架",
    ],
}


class IntentClassification(BaseModel):
    mode: ChatMode
    confidence: float = 0.0
    reasoning: str = ""


def classify_by_keywords(message: str) -> ChatMode:
    """Keyword-based fallback when the model is not available."""
    normalized = message.casefold()
    for mode, words in _KEYWORDS.items():
        if any(word.casefold() in normalized for word in words):
            return mode
    return ChatMode.OTHER


async def classify_intent(
    gateway: ModelGateway,
    content: str,
) -> IntentClassification:
    """Classify the user's intent with the fast router model."""
    try:
        parts = [
            token
            async for token in gateway.stream_chat(
                [
                    {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": content[:1500]},
                ]
            )
        ]
        response = "".join(parts).strip()
        mode = _parse_mode_label(response) or classify_by_keywords(content)
        return IntentClassification(
            mode=mode,
            confidence=1.0,
            reasoning="fast router model",
        )
    except Exception:
        return IntentClassification(
            mode=classify_by_keywords(content),
            confidence=0.0,
            reasoning="Model unavailable, using keyword fallback",
        )


def _parse_mode_label(text: str) -> Optional[ChatMode]:
    normalized = text.strip().strip("` \n\r\t。：:，,")
    if normalized in _LABEL_TO_MODE:
        return _LABEL_TO_MODE[normalized]
    for label, mode in _LABEL_TO_MODE.items():
        if label in normalized:
            return mode
    return None
