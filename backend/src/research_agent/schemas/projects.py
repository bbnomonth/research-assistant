from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from research_agent.db.models import ConversationSession, Message, Project


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    profile: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def require_update(self):
        if self.name is None and self.profile is None:
            raise ValueError("name or profile is required")
        return self


class ProjectResponse(BaseModel):
    id: str
    name: str
    profile: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, project: Project) -> "ProjectResponse":
        return cls(
            id=project.id,
            name=project.name,
            profile=json.loads(project.profile_json or "{}"),
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]


class SessionResponse(BaseModel):
    id: str
    project_id: str
    summary: str
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        session: ConversationSession,
    ) -> "SessionResponse":
        return cls(
            id=session.id,
            project_id=session.project_id,
            summary=session.summary,
            created_at=session.created_at,
        )


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    mode: Optional[str]
    sequence: int
    created_at: datetime

    @classmethod
    def from_model(cls, message: Message) -> "MessageResponse":
        return cls(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            mode=message.mode,
            sequence=message.sequence,
            created_at=message.created_at,
        )


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
