from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from research_agent.db.models import ConversationSession, Message, Paper, Project


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


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)


class SessionResponse(BaseModel):
    id: str
    project_id: str
    title: str
    summary: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        session: ConversationSession,
    ) -> "SessionResponse":
        return cls(
            id=session.id,
            project_id=session.project_id,
            title=session.title or "",
            summary=session.summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    mode: Optional[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)
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
            metadata=json.loads(message.metadata_json or "{}"),
            sequence=message.sequence,
            created_at=message.created_at,
        )


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]


class PaperSummary(BaseModel):
    id: str
    project_id: str
    arxiv_id: str
    title: str
    authors_json: str
    abstract: str
    published: str
    categories_json: str
    entry_url: str
    pdf_url: str
    recommendation_reason: str
    purpose_labels_json: str
    favorited: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, paper: Paper) -> "PaperSummary":
        return cls(
            id=paper.id,
            project_id=paper.project_id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors_json=paper.authors_json,
            abstract=paper.abstract,
            published=paper.published,
            categories_json=paper.categories_json,
            entry_url=paper.entry_url,
            pdf_url=paper.pdf_url,
            recommendation_reason=paper.recommendation_reason,
            purpose_labels_json=paper.purpose_labels_json,
            favorited=paper.favorited,
            created_at=paper.created_at,
            updated_at=paper.updated_at,
        )


class PaperListResponse(BaseModel):
    papers: List[PaperSummary] = Field(default_factory=list)
