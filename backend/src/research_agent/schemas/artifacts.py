import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from research_agent.db.models import Artifact


class ArtifactResponse(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    content: Dict[str, Any]
    markdown: str
    created_at: datetime

    @classmethod
    def from_model(cls, artifact: Artifact) -> "ArtifactResponse":
        return cls(
            id=artifact.id,
            project_id=artifact.project_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            content=json.loads(artifact.content_json or "{}"),
            markdown=artifact.markdown,
            created_at=artifact.created_at,
        )


class ArtifactSummary(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    created_at: datetime

    @classmethod
    def from_model(cls, artifact: Artifact) -> "ArtifactSummary":
        return cls(
            id=artifact.id,
            project_id=artifact.project_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            created_at=artifact.created_at,
        )


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactSummary]


class ArtifactUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[Dict[str, Any]] = None
    markdown: Optional[str] = None
