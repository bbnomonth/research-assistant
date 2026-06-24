from sqlalchemy import func, select

from research_agent.db.engine import Database
from research_agent.db.models import Paper
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper


def test_upsert_deduplicates_arxiv_versions(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    paper_v1 = ArxivPaper(
        arxiv_id="2305.05665",
        title="A paper",
        authors=["A. Author"],
        abstract="Abstract",
        published="2023-05-09",
        categories=["cs.AI"],
        entry_url="https://arxiv.org/abs/2305.05665v1",
        pdf_url="https://arxiv.org/pdf/2305.05665v1",
    )
    paper_v2 = paper_v1.model_copy(
        update={
            "title": "A paper revised",
            "entry_url": "https://arxiv.org/abs/2305.05665v2",
        }
    )

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        repository = PaperRepository(db)
        repository.upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=paper_v1,
                    reason="初次推荐",
                    purpose_labels=["方法相似"],
                ),
                RecommendedPaper(
                    paper=paper_v2,
                    reason="更新推荐",
                    purpose_labels=["前沿文献"],
                ),
            ],
        )
        db.commit()

        count = db.scalar(select(func.count()).select_from(Paper))
        stored = db.scalar(select(Paper))

    assert count == 1
    assert stored is not None
    assert stored.title == "A paper revised"
    assert stored.recommendation_reason == "更新推荐"
