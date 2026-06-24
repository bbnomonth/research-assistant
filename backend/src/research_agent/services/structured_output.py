from dataclasses import dataclass
import json
import re
from typing import Callable, Generic, TypeVar

from research_agent.services.model_gateway import ModelGateway, collect_chat


T = TypeVar("T")
JSON_FENCE = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json(text: str):
    stripped = text.strip()
    match = JSON_FENCE.search(stripped)
    if match:
        stripped = match.group(1).strip()
    return json.loads(stripped)


@dataclass(frozen=True)
class StructuredOutputResult(Generic[T]):
    value: T
    retries: int


async def validate_structured(
    gateway: ModelGateway,
    prompt: str,
    validator: Callable[[object], T],
    fallback: T,
) -> StructuredOutputResult[T]:
    response = await collect_chat(
        gateway,
        [{"role": "user", "content": prompt}],
    )
    try:
        return StructuredOutputResult(
            value=validator(extract_json(response)),
            retries=0,
        )
    except (ValueError, TypeError):
        repair_prompt = (
            "Repair the following response into valid JSON matching the "
            "original requested schema. Return JSON only. Do not add new facts."
            f"\nOriginal request: {prompt}"
            f"\nResponse to repair: {response}"
        )
        repaired = await collect_chat(
            gateway,
            [{"role": "user", "content": repair_prompt}],
        )
        try:
            value = validator(extract_json(repaired))
        except (ValueError, TypeError):
            value = fallback
        return StructuredOutputResult(value=value, retries=1)
