import asyncio

from research_agent.services.model_gateway import (
    FakeModelGateway,
    build_qwen_messages,
)


def test_build_qwen_messages_keeps_only_recent_context() -> None:
    history = [
        {"role": "user", "content": f"question-{i}"}
        for i in range(25)
    ]

    messages = build_qwen_messages(history, "latest", history_limit=20)

    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "latest"}
    assert all("question-0" not in item["content"] for item in messages)
    assert any("question-24" in item["content"] for item in messages)


def test_fake_gateway_streams_tokens() -> None:
    async def collect():
        gateway = FakeModelGateway(["第一段", "第二段"])
        return [token async for token in gateway.stream_chat([])]

    assert asyncio.run(collect()) == ["第一段", "第二段"]
