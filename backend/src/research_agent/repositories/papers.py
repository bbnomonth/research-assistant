import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_agent.db.models import Paper
from research_agent.schemas.literature import RecommendedPaper


class PaperRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_arxiv_papers(
        self,
        project_id: str,
        recommendations: List[RecommendedPaper],
    ) -> List[Paper]:
        stored = []
        for recommendation in recommendations:
            source = recommendation.paper
            paper = self.db.scalar(
                select(Paper).where(
                    Paper.project_id == project_id,
                    Paper.arxiv_id == source.arxiv_id,
                )
            )
            if paper is None:
                paper = Paper(project_id=project_id, arxiv_id=source.arxiv_id)
                self.db.add(paper)

            paper.title = source.title
            paper.authors_json = json.dumps(
                source.authors,
                ensure_ascii=False,
            )
            paper.abstract = source.abstract
            paper.published = source.published
            paper.categories_json = json.dumps(source.categories)
            paper.entry_url = source.entry_url
            paper.pdf_url = source.pdf_url
            paper.recommendation_reason = recommendation.reason
            paper.purpose_labels_json = json.dumps(
                recommendation.purpose_labels,
                ensure_ascii=False,
            )
            self.db.flush()
            stored.append(paper)
        return stored

    def list_for_project(self, project_id: str, limit: int = 20) -> List[Paper]:
        return list(
            self.db.scalars(
                select(Paper)
                .where(Paper.project_id == project_id)
                .order_by(Paper.created_at.desc())
                .limit(limit)
            )
        )

    def list_for_evidence(self, project_id: str) -> List[Paper]:
        """Return papers eligible for evidence-based features: favorited or uploaded."""
        return list(
            self.db.scalars(
                select(Paper)
                .where(
                    Paper.project_id == project_id,
                    (Paper.favorited == True) | (Paper.arxiv_id.like("upload:%")),
                )
                .order_by(Paper.created_at.desc())
            )
        )

    def toggle_favorite(self, project_id: str, arxiv_id: str, favorited: bool) -> Optional[Paper]:
        paper = self.db.scalar(
            select(Paper).where(
                Paper.project_id == project_id,
                Paper.arxiv_id == arxiv_id,
            )
        )
        if paper is not None:
            paper.favorited = favorited
        return paper
