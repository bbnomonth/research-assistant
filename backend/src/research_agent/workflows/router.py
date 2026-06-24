from typing import Optional

from langgraph.graph import END, START, StateGraph
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
        "arxiv",
        "search papers",
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


def _general_qa(_: RouterState) -> RouterState:
    return {"workflow_status": "ready"}


def _not_implemented(_: RouterState) -> RouterState:
    return {"workflow_status": "not_implemented"}


def _mode_name(state: RouterState) -> str:
    return state["mode"].value


def build_router_graph():
    builder = StateGraph(RouterState)
    builder.add_node("route", _route)
    builder.add_node(ChatMode.GENERAL_QA.value, _general_qa)
    builder.add_node(ChatMode.LITERATURE_DISCOVERY.value, _not_implemented)
    builder.add_node(ChatMode.PAPER_READING.value, _not_implemented)
    builder.add_node(ChatMode.RESEARCH_DIAGNOSIS.value, _not_implemented)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        _mode_name,
        {
            ChatMode.GENERAL_QA.value: ChatMode.GENERAL_QA.value,
            ChatMode.LITERATURE_DISCOVERY.value:
                ChatMode.LITERATURE_DISCOVERY.value,
            ChatMode.PAPER_READING.value: ChatMode.PAPER_READING.value,
            ChatMode.RESEARCH_DIAGNOSIS.value:
                ChatMode.RESEARCH_DIAGNOSIS.value,
        },
    )
    builder.add_edge(ChatMode.GENERAL_QA.value, END)
    builder.add_edge(ChatMode.LITERATURE_DISCOVERY.value, END)
    builder.add_edge(ChatMode.PAPER_READING.value, END)
    builder.add_edge(ChatMode.RESEARCH_DIAGNOSIS.value, END)
    return builder.compile()
