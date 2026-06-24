import json
from typing import Dict, Optional

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

    def to_markdown(self, artifact_id: str) -> str:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise LookupError("artifact not found")
        return artifact.markdown
