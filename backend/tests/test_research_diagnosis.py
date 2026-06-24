import asyncio
import json

from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper
from research_agent.services.research_diagnosis import ResearchDiagnosisService


class DiagnosisGateway:
    model_name = "fake"

    def __init__(self) -> None:
        self.prompt = ""

    async def stream_chat(self, messages):
        self.prompt = messages[-1]["content"]
        yield """{
          "topic_summary": "Routing with machine learning",
          "evidence_supported_judgements": ["Existing evidence mentions routing."],
          "reasonable_inferences": ["The project may need method narrowing."],
          "gaps": ["Data source is unclear."],
          "risks": ["Scope may be broad."],
          "next_questions": ["What dataset will be used?"]
        }"""


def test_research_diagnosis_creates_evidence_bound_artifact(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        paper = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id="2401.20001",
                        title="Routing Diagnosis Paper",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url="https://arxiv.org/abs/2401.20001",
                        pdf_url="https://arxiv.org/pdf/2401.20001",
                    ),
                    reason="",
                    purpose_labels=[],
                )
            ],
        )[0]
        stored = PaperChunkRepository(db).replace_chunks(
            paper.id,
            [
                {
                    "page_number": 1,
                    "chunk_index": 1,
                    "section": "Introduction",
                    "text": "Vehicle routing evidence for diagnosis.",
                    "is_ocr": False,
                }
            ],
        )
        gateway = DiagnosisGateway()
        result = asyncio.run(
            ResearchDiagnosisService(db, gateway).diagnose(
                project.id,
                "诊断我的车辆路径优化选题",
            )
        )
        db.commit()

    assert result.artifact.artifact_type == "research_diagnosis"
    assert result.evidence_pages[paper.id] == [1]
    assert "Vehicle routing evidence" in gateway.prompt
    assert "Data source is unclear" in result.artifact.markdown

    content = json.loads(result.artifact.content_json)
    assert content["evidence"][paper.id][0]["chunk_id"] == stored[0].id
