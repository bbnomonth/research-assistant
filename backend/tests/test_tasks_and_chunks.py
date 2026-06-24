from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.repositories.tasks import TaskRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper


def _paper(project_id: str, db):
    source = ArxivPaper(
        arxiv_id="2401.00001",
        title="PDF Test",
        authors=["A"],
        abstract="A",
        published="2024-01-01",
        categories=["cs.AI"],
        entry_url="https://arxiv.org/abs/2401.00001",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )
    return PaperRepository(db).upsert_arxiv_papers(
        project_id,
        [RecommendedPaper(paper=source, reason="", purpose_labels=[])],
    )[0]


def test_task_state_and_fts_chunk_search(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        paper = _paper(project.id, db)
        task_repo = TaskRepository(db)
        task = task_repo.create_task("parse_pdf", paper_id=paper.id)
        task_repo.update_status(task.id, "completed", progress=100)

        chunk_repo = PaperChunkRepository(db)
        chunk_repo.replace_chunks(
            paper.id,
            [
                {
                    "page_number": 1,
                    "chunk_index": 1,
                    "section": "Introduction",
                    "text": "Vehicle routing with machine learning evidence.",
                    "is_ocr": False,
                }
            ],
        )
        db.commit()

        results = chunk_repo.search(paper.id, "machine learning")

    assert task.status == "completed"
    assert results[0].page_number == 1
    assert "machine learning" in results[0].text
