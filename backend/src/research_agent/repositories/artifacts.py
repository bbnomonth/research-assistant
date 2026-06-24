import json
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact


class ArtifactRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_artifact(
        self,
        project_id: str,
        artifact_type: str,
        title: str,
        content: Dict,
        markdown: str,
    ) -> Artifact:
        artifact = Artifact(
            project_id=project_id,
            artifact_type=artifact_type,
            title=title,
            content_json=json.dumps(content, ensure_ascii=False),
            markdown=markdown,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self.db.get(Artifact, artifact_id)

    def list_for_project(self, project_id: str) -> List[Artifact]:
        return list(
            self.db.scalars(
                select(Artifact)
                .where(Artifact.project_id == project_id)
                .order_by(Artifact.created_at.desc())
            )
        )

    def update_artifact(
        self,
        artifact_id: str,
        title: Optional[str] = None,
        content: Optional[Dict] = None,
        markdown: Optional[str] = None,
    ) -> Artifact:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise LookupError("artifact not found")
        if title is not None:
            artifact.title = title
        if content is not None:
            artifact.content_json = json.dumps(content, ensure_ascii=False)
        if markdown is not None:
            artifact.markdown = markdown
        self.db.flush()
        return artifact

    def to_markdown(self, artifact_id: str) -> str:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise LookupError("artifact not found")
        return artifact.markdown
