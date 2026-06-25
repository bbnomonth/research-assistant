from typing import Optional

from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from research_agent.schemas.chat import ChatMode


class RouterState(TypedDict, total=False):
    content: str
    mode_override: Optional[ChatMode]
    mode: ChatMode
    workflow_status: str


KEYWORDS = {
    ChatMode.LITERATURE_DISCOVERY: (
        "搜索",
        "检索",
        "文献推荐",
        "找文献",
        "search papers",
        "最新论文",
        "论文检索",
        "查找论文",
        "帮我找",
        "有什么相关",
        "推荐一些",
    ),
    ChatMode.PAPER_READING: (
        "pdf",
        "精读",
        "这篇文章",
        "这篇论文",
        "上传的",
        "paper reading",
    ),
    ChatMode.RESEARCH_DIAGNOSIS: (
        "选题",
        "研究框架",
        "研究设计",
        "论文框架",
        "开题",
        "诊断",
        "diagnose",
    ),
}


def classify_mode(message: str) -> ChatMode:
    normalized = message.casefold()
    for mode, words in KEYWORDS.items():
        if any(word.casefold() in normalized for word in words):
            return mode
    return ChatMode.GENERAL_QA


def _route(state: RouterState) -> RouterState:
    mode = state.get("mode_override") or classify_mode(state["content"])
    return {"mode": mode}


def build_router_graph():
    builder = StateGraph(RouterState)
    builder.add_node("route", _route)
    builder.add_edge(START, "route")
    return builder.compile()
