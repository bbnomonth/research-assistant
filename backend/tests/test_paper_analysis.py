import asyncio
import json

from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper
from research_agent.services.paper_analysis import PaperAnalysisService


class AnalysisGateway:
    model_name = "fake"

    def __init__(self) -> None:
        self.prompt = ""
        self.calls = 0

    async def stream_chat(self, messages):
        self.calls += 1
        self.prompt = messages[-1]["content"]
        if "中文对比报告" in self.prompt:
            yield "# 论文对比报告\n\n两篇论文都研究 routing，但方法证据不同。"
            return
        assert "Vehicle routing evidence" in self.prompt
        yield "# 论文解读\n\nHow is ML used in routing? Page 1 evidence is relevant."


def test_quick_analysis_creates_artifact_from_chunks(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        paper = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id="2401.00001",
                        title="Routing Paper",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url="https://arxiv.org/abs/2401.00001",
                        pdf_url="https://arxiv.org/pdf/2401.00001",
                    ),
                    reason="",
                    purpose_labels=[],
                )
            ],
        )[0]
        paper.favorited = True
        stored_chunks = PaperChunkRepository(db).replace_chunks(
            paper.id,
            [
                {
                    "page_number": 1,
                    "chunk_index": 1,
                    "section": "",
                    "text": "Vehicle routing evidence from page one.",
                    "is_ocr": False,
                },
                *[
                    {
                        "page_number": index,
                        "chunk_index": index,
                        "section": "Background",
                        "text": f"Background filler chunk {index}.",
                        "is_ocr": False,
                    }
                    for index in range(2, 11)
                ],
                {
                    "page_number": 11,
                    "chunk_index": 11,
                    "section": "Method",
                    "text": "Method section explains model training evidence.",
                    "is_ocr": False,
                },
            ],
        )
        gateway = AnalysisGateway()
        result = asyncio.run(
            PaperAnalysisService(db, gateway).quick_analyze(paper.id)
        )
        db.commit()

    assert result.artifact.title == "论文解读：Routing Paper"
    assert result.evidence_pages == [1, 11]
    assert "Method section explains" in gateway.prompt
    assert "完整全面的论文解读" in gateway.prompt
    assert "How is ML used" in result.artifact.markdown
    assert "Page 1" in result.artifact.markdown

    content = json.loads(result.artifact.content_json)
    assert content["evidence"][0]["chunk_id"] == stored_chunks[0].id
    assert content["evidence"][0]["page_number"] == 1


def test_quick_analysis_does_not_call_model_without_chunks(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        paper = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id="2401.00999",
                        title="Unparsed Paper",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url="https://arxiv.org/abs/2401.00999",
                        pdf_url="https://arxiv.org/pdf/2401.00999",
                    ),
                    reason="",
                    purpose_labels=[],
                )
            ],
        )[0]
        paper.favorited = True
        gateway = AnalysisGateway()
        result = asyncio.run(
            PaperAnalysisService(db, gateway).quick_analyze(paper.id)
        )
        db.commit()

    assert gateway.calls == 0
    assert result.artifact.markdown.startswith("# Unparsed Paper 论文解读")
    assert "暂无已解析正文" in result.artifact.markdown
    assert "尊敬的" not in result.artifact.markdown


def test_compare_papers_creates_evidence_bound_artifact(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        papers = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id=f"2401.0000{index}",
                        title=f"Routing Paper {index}",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url=f"https://arxiv.org/abs/2401.0000{index}",
                        pdf_url=f"https://arxiv.org/pdf/2401.0000{index}",
                    ),
                    reason="",
                    purpose_labels=[],
                )
                for index in (1, 2)
            ],
        )
        for paper in papers:
            paper.favorited = True
        for index, paper in enumerate(papers, start=1):
            PaperChunkRepository(db).replace_chunks(
                paper.id,
                [
                    {
                        "page_number": 1,
                        "chunk_index": 1,
                        "section": "Introduction",
                        "text": f"Vehicle routing evidence for paper {index}.",
                        "is_ocr": False,
                    },
                    {
                        "page_number": 3,
                        "chunk_index": 2,
                        "section": "Method",
                        "text": f"Method evidence for paper {index}.",
                        "is_ocr": False,
                    },
                ],
            )

        gateway = AnalysisGateway()
        result = asyncio.run(
            PaperAnalysisService(db, gateway).compare_papers(
                [paper.id for paper in papers]
            )
        )
        db.commit()

    assert result.artifact.title.startswith("论文对比：")
    assert result.evidence_pages[papers[0].id] == [1, 3]
    assert "Routing Paper 1" in gateway.prompt
    assert "Routing Paper 2" in gateway.prompt
    assert "中文对比报告" in gateway.prompt
    assert result.artifact.markdown.startswith("# 论文对比报告")

    content = json.loads(result.artifact.content_json)
    assert content["papers"][0]["paper_id"] == papers[0].id
    assert content["evidence"][papers[0].id][0]["page_number"] == 1
