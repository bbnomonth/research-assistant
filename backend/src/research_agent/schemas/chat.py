from enum import Enum
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    GENERAL_QA = "general_qa"
    LITERATURE_DISCOVERY = "literature_discovery"
    PAPER_READING = "paper_reading"
    RESEARCH_DIAGNOSIS = "research_diagnosis"


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    mode_override: Optional[ChatMode] = None


class StreamEvent(BaseModel):
    event: str
    data: Dict[str, Any]

    def to_sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"

