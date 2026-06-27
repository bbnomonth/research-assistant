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


class ArtifactSourceLink(BaseModel):
    source_type: str
    target_id: str
    label: str
    project_id: Optional[str] = None


class ArtifactSummary(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    created_at: datetime
    source_links: List[ArtifactSourceLink] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls,
        artifact: Artifact,
        source_links: Optional[List[ArtifactSourceLink]] = None,
    ) -> "ArtifactSummary":
        content = json.loads(artifact.content_json or "{}")
        return cls(
            id=artifact.id,
            project_id=artifact.project_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            created_at=artifact.created_at,
            source_links=source_links
            if source_links is not None
            else extract_source_links(
                artifact_type=artifact.artifact_type,
                project_id=artifact.project_id,
                content=content,
            ),
        )


class ArtifactListResponse(BaseModel):
    artifacts: List[ArtifactSummary]


class ArtifactUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[Dict[str, Any]] = None
    markdown: Optional[str] = None


def extract_source_links(
    artifact_type: str,
    project_id: str,
    content: Dict[str, Any],
) -> List[ArtifactSourceLink]:
    links: List[ArtifactSourceLink] = []
    session_id = content.get("source_session_id") or content.get("session_id")
    if isinstance(session_id, str) and session_id:
        links.append(
            ArtifactSourceLink(
                source_type="session",
                target_id=session_id,
                project_id=project_id,
                label="来源对话",
            )
        )

    paper_id = content.get("paper_id")
    if isinstance(paper_id, str) and paper_id:
        links.append(
            ArtifactSourceLink(
                source_type="paper",
                target_id=paper_id,
                project_id=project_id,
                label="来源论文",
            )
        )

    papers = content.get("papers")
    if isinstance(papers, list):
        for index, item in enumerate(papers, start=1):
            if not isinstance(item, dict):
                continue
            linked_paper_id = item.get("paper_id")
            if not isinstance(linked_paper_id, str) or not linked_paper_id:
                continue
            title = item.get("title")
            label = f"对比论文 {index}"
            if isinstance(title, str) and title:
                label = title[:40]
            links.append(
                ArtifactSourceLink(
                    source_type="paper",
                    target_id=linked_paper_id,
                    project_id=project_id,
                    label=label,
                )
            )

    if artifact_type == "literature_card" and not any(
        link.source_type == "paper" for link in links
    ):
        embedded_paper_id = content.get("id")
        if isinstance(embedded_paper_id, str) and embedded_paper_id:
            links.append(
                ArtifactSourceLink(
                    source_type="paper",
                    target_id=embedded_paper_id,
                    project_id=project_id,
                    label="来源论文",
                )
            )

    return links
