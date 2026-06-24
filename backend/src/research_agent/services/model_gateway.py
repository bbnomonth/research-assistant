from collections.abc import AsyncIterator
from typing import Dict, List, Protocol, Sequence

from openai import AsyncOpenAI


SYSTEM_PROMPT = """你是论文研究能力训练助手。
普通知识问题应直接、准确回答。
不要编造文献、数据、实验结果或原文证据。
区分已有依据、合理推断和需要补充证据的内容。
回答使用中文，除非用户明确要求其他语言。"""


class ModelGatewayError(RuntimeError):
    """Safe model error that never includes credentials or prompt content."""


class ModelGateway(Protocol):
    model_name: str

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        pass


def build_qwen_messages(
    history: Sequence[Dict[str, str]],
    current_content: str,
    history_limit: int = 20,
) -> List[Dict[str, str]]:
    recent = list(history[-history_limit:])
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *recent,
        {"role": "user", "content": current_content},
    ]


class FakeModelGateway:
    model_name = "fake-model"

    def __init__(self, tokens: Sequence[str]) -> None:
        self._tokens = list(tokens)

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        del messages
        for token in self._tokens:
            yield token

    async def aclose(self) -> None:
        return None


class QwenOpenAIGateway:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        max_output_tokens: int = 2_048,
    ) -> None:
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        emitted = False
        for attempt in range(2):
            try:
                stream = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=self.max_output_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    token = getattr(delta, "content", None)
                    if token:
                        emitted = True
                        yield token
                return
            except Exception as exc:
                if attempt == 0 and not emitted:
                    continue
                raise ModelGatewayError(
                    "模型服务暂时不可用，请检查百炼配置或稍后重试。"
                ) from exc

    async def aclose(self) -> None:
        await self._client.close()


async def collect_chat(
    gateway: ModelGateway,
    messages: List[Dict[str, str]],
) -> str:
    parts = [
        token
        async for token in gateway.stream_chat(messages)
    ]
    return "".join(parts)
