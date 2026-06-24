import asyncio
from types import SimpleNamespace

from research_agent.services.model_gateway import (
    FakeModelGateway,
    QwenOpenAIGateway,
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


def test_qwen_gateway_ignores_stream_chunks_without_choices() -> None:
    class FakeCompletions:
        async def create(self, **kwargs):
            del kwargs

            async def chunks():
                yield SimpleNamespace(choices=[])
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="OK")
                        )
                    ]
                )

            return chunks()

    async def collect():
        gateway = QwenOpenAIGateway(
            api_key="not-a-real-key",
            base_url="https://example.invalid",
            model_name="test-model",
        )
        gateway._client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        return [
            token
            async for token in gateway.stream_chat(
                [{"role": "user", "content": "test"}]
            )
        ]

    assert asyncio.run(collect()) == ["OK"]


def test_qwen_gateway_closes_underlying_client() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    async def close_gateway() -> bool:
        gateway = QwenOpenAIGateway(
            api_key="not-a-real-key",
            base_url="https://example.invalid",
            model_name="test-model",
        )
        fake_client = FakeClient()
        gateway._client = fake_client
        await gateway.aclose()
        return fake_client.closed

    assert asyncio.run(close_gateway()) is True
