from enum import Enum
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    OTHER = "other"
    LITERATURE_DISCOVERY = "literature_discovery"
    PAPER_READING = "paper_reading"
    TOPIC_GUIDANCE = "topic_guidance"
    FRAMEWORK_BUILDING = "framework_building"


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    paper_id: Optional[str] = None
    mode_override: Optional[ChatMode] = None


class FrameworkCardRequest(BaseModel):
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class TopicGuidanceCardRequest(BaseModel):
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class StreamEvent(BaseModel):
    event: str
    data: Dict[str, Any]

    def to_sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"
