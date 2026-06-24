import asyncio

from pydantic import BaseModel

from research_agent.services.structured_output import validate_structured


class OutputModel(BaseModel):
    value: str


class ScriptedGateway:
    model_name = "fake"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def stream_chat(self, messages):
        del messages
        self.calls += 1
        yield self.responses.pop(0)


def test_structured_output_does_not_retry_valid_json() -> None:
    gateway = ScriptedGateway(['{"value":"ok"}'])

    result = asyncio.run(
        validate_structured(
            gateway=gateway,
            prompt="Return JSON",
            validator=OutputModel.model_validate,
            fallback=OutputModel(value="fallback"),
        )
    )

    assert result.value.value == "ok"
    assert result.retries == 0
    assert gateway.calls == 1


def test_structured_output_repairs_invalid_json_once() -> None:
    gateway = ScriptedGateway(["not-json", '{"value":"repaired"}'])

    result = asyncio.run(
        validate_structured(
            gateway=gateway,
            prompt="Return JSON",
            validator=OutputModel.model_validate,
            fallback=OutputModel(value="fallback"),
        )
    )

    assert result.value.value == "repaired"
    assert result.retries == 1
    assert gateway.calls == 2


def test_structured_output_uses_fallback_after_one_failed_repair() -> None:
    gateway = ScriptedGateway(["not-json", "still-not-json"])

    result = asyncio.run(
        validate_structured(
            gateway=gateway,
            prompt="Return JSON",
            validator=OutputModel.model_validate,
            fallback=OutputModel(value="fallback"),
        )
    )

    assert result.value.value == "fallback"
    assert result.retries == 1
    assert gateway.calls == 2
