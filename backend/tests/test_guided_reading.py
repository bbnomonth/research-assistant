import asyncio

import pytest

from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper
from research_agent.services.guided_reading import GuidedReadingService


class ReadingGateway:
    model_name = "fake"

    def __init__(self, completed: bool) -> None:
        self.completed = completed
        self.prompt = ""

    async def stream_chat(self, messages):
        self.prompt = "\n".join(item["content"] for item in messages)
        if self.completed:
            yield "你已经完成了主要精读路径。请回到第 2 页核对方法证据，并用一句话说明它如何支撑论文贡献。"
            return
        yield "你已经识别出研究对象，但还需要回到第 2 页确认方法证据：作者具体使用了什么方法来处理车辆路径问题？"


class FinalSummaryGateway:
    model_name = "fake"

    async def stream_chat(self, messages):
        del messages
        yield (
            "Final summary: this paper studies vehicle routing. "
            "Research question: how to improve routing decisions. "
            "Method: learning-guided optimization. "
            "Evidence: method evidence appears on page 2. "
            "Contribution: it connects learning and routing. "
            "Limitation: more validation is still needed."
        )


def _create_paper_with_evidence(db):
    project, session = ConversationRepository(db).ensure_conversation(None, None)
    paper = PaperRepository(db).upsert_arxiv_papers(
        project.id,
        [
            RecommendedPaper(
                paper=ArxivPaper(
                    arxiv_id="2401.30001",
                    title="Guided Routing Paper",
                    authors=["A"],
                    abstract="Abstract",
                    published="2024-01-01",
                    categories=["cs.AI"],
                    entry_url="https://arxiv.org/abs/2401.30001",
                    pdf_url="https://arxiv.org/pdf/2401.30001",
                ),
                reason="",
                purpose_labels=[],
            )
        ],
    )[0]
    paper.favorited = True
    chunks = PaperChunkRepository(db).replace_chunks(
        paper.id,
        [
            {
                "page_number": 2,
                "chunk_index": 1,
                "section": "Method",
                "text": "The paper uses a learning-guided vehicle routing method.",
                "is_ocr": False,
            }
        ],
    )
    return project, session, paper, chunks


def test_guided_reading_returns_feedback_without_artifact(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _, paper, chunks = _create_paper_with_evidence(db)
        gateway = ReadingGateway(completed=False)
        result = asyncio.run(
            GuidedReadingService(db, gateway).guide(
                project_id=project.id,
                paper_id=paper.id,
                user_input="这篇论文研究车辆路径问题。",
                history=[],
            )
        )

    assert result.artifact is None
    assert result.turn.next_question == ""
    assert "作者具体使用了什么方法" in result.turn.feedback
    assert result.evidence_pages == [2]
    assert chunks[0].id in gateway.prompt
    assert "learning-guided vehicle routing" in gateway.prompt
    assert "苏格拉底式提问法" in gateway.prompt
    assert "每次优先提出 1 个关键问题" in gateway.prompt
    assert "始终要求回到原文" in gateway.prompt
    assert "论文原文片段" in gateway.prompt


def test_guided_reading_completion_waits_for_card_confirmation(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _, paper, _ = _create_paper_with_evidence(db)
        result = asyncio.run(
            GuidedReadingService(db, ReadingGateway(completed=True)).guide(
                project_id=project.id,
                paper_id=paper.id,
                user_input="作者使用学习引导的路径优化方法。",
                history=[
                    {"role": "assistant", "content": "现在检查局限与边界。"},
                    {"role": "user", "content": "车辆路径问题。"},
                ],
            )
        )
        db.commit()

    assert result.turn.completed is True
    assert result.artifact is None


def test_guided_reading_rejects_paper_from_another_project(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _, paper, _ = _create_paper_with_evidence(db)
        other_project, _ = ConversationRepository(db).ensure_conversation(None, None)

        with pytest.raises(ValueError, match="paper does not belong"):
            asyncio.run(
                GuidedReadingService(db, ReadingGateway(False)).guide(
                    project_id=other_project.id,
                    paper_id=paper.id,
                    user_input="开始精读",
                    history=[],
                )
            )

        assert project.id != other_project.id


def test_guided_reading_marks_final_summary_text_as_completed(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _, paper, _ = _create_paper_with_evidence(db)
        result = asyncio.run(
            GuidedReadingService(db, FinalSummaryGateway()).guide(
                project_id=project.id,
                paper_id=paper.id,
                user_input="Please give the final explanation.",
                history=[],
            )
        )

    assert result.turn.completed is True
    assert result.artifact is None


def test_guided_reading_rejects_paper_without_evidence(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _, paper, _ = _create_paper_with_evidence(db)
        PaperChunkRepository(db).replace_chunks(paper.id, [])

        with pytest.raises(ValueError, match="no parsed evidence"):
            asyncio.run(
                GuidedReadingService(db, ReadingGateway(False)).guide(
                    project_id=project.id,
                    paper_id=paper.id,
                    user_input="开始精读",
                    history=[],
                )
            )
