import pytest

from research_agent.schemas.chat import ChatMode
from research_agent.workflows.router import build_router_graph, classify_mode


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("帮我搜索物流调度相关论文", ChatMode.LITERATURE_DISCOVERY),
        ("分析我刚上传的这篇PDF", ChatMode.PAPER_READING),
        ("这个选题和研究框架合理吗", ChatMode.RESEARCH_DIAGNOSIS),
        ("诊断我的车辆路径优化选题", ChatMode.RESEARCH_DIAGNOSIS),
        ("什么是混合整数规划", ChatMode.GENERAL_QA),
    ],
)
def test_rule_first_classification(message, expected) -> None:
    assert classify_mode(message) is expected


def test_graph_classifies_mode_from_message() -> None:
    graph = build_router_graph()

    result = graph.invoke({"content": "搜索人工智能论文"})

    assert result["mode"] == ChatMode.LITERATURE_DISCOVERY


def test_graph_classifies_general_qa() -> None:
    graph = build_router_graph()

    result = graph.invoke({"content": "什么是运筹学"})

    assert result["mode"] == ChatMode.GENERAL_QA


def test_mode_override_wins() -> None:
    graph = build_router_graph()

    result = graph.invoke(
        {
            "content": "什么是运筹学",
            "mode_override": ChatMode.RESEARCH_DIAGNOSIS,
        }
    )

    assert result["mode"] == ChatMode.RESEARCH_DIAGNOSIS
