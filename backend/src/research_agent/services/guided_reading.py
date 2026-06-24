from dataclasses import dataclass
import json
import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact, Paper
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.paper_chunks import EvidenceResult, PaperChunkRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway
from research_agent.services.structured_output import validate_structured


class GuidedReadingTurn(BaseModel):
    feedback: str = ""
    evidence_notes: List[str] = Field(default_factory=list)
    next_question: str = ""
    completed: bool = False
    learning_summary: str = ""


@dataclass(frozen=True)
class GuidedReadingResult:
    turn: GuidedReadingTurn
    evidence: List[EvidenceResult]
    artifact: Optional[Artifact] = None

    @property
    def evidence_pages(self) -> List[int]:
        pages = []
        for item in self.evidence:
            if item.page_number not in pages:
                pages.append(item.page_number)
        return pages


class GuidedReadingService:
    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.model_gateway = model_gateway

    async def guide(
        self,
        project_id: str,
        paper_id: str,
        user_input: str,
        history: List[Dict[str, str]],
    ) -> GuidedReadingResult:
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            raise LookupError("paper not found")
        if paper.project_id != project_id:
            raise ValueError("paper does not belong to project")

        evidence = PaperChunkRepository(self.db).list_for_paper(
            paper_id,
            limit=8,
        )
        if not evidence:
            raise ValueError("paper has no parsed evidence")

        turn = await self._build_turn(
            paper=paper,
            user_input=user_input,
            history=history[-12:],
            evidence=evidence,
        )
        artifact = None
        if turn.completed:
            artifact = self._create_artifact(paper, turn, evidence)
        return GuidedReadingResult(
            turn=turn,
            evidence=evidence,
            artifact=artifact,
        )

    async def _build_turn(
        self,
        paper: Paper,
        user_input: str,
        history: List[Dict[str, str]],
        evidence: List[EvidenceResult],
    ) -> GuidedReadingTurn:
        payload = [
            {
                "chunk_id": item.chunk_id,
                "page": item.page_number,
                "section": item.section,
                "text": item.text[:1200],
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        prompt = (
            "Act as an evidence-bound guided reading coach. Use only the "
            "supplied paper evidence. Give concise feedback on the learner's "
            "answer and ask at most one next question. Mark completed true only "
            "when the learner has demonstrated a useful understanding of the "
            "research question, method, and contribution. Return JSON only with "
            "keys: feedback, evidence_notes, next_question, completed, "
            "learning_summary.\n"
            f"Paper title: {paper.title}\n"
            f"Recent reading dialogue: {json.dumps(history, ensure_ascii=False)}\n"
            f"Learner answer: {user_input}\n"
            f"Evidence: {json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = GuidedReadingTurn(
            feedback="本轮引导结果无法解析，请结合原文证据重新回答。",
            next_question="请概括论文的研究问题，并指出支持该判断的页码。",
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=GuidedReadingTurn.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    def _create_artifact(
        self,
        paper: Paper,
        turn: GuidedReadingTurn,
        evidence: List[EvidenceResult],
    ) -> Artifact:
        evidence_content = [
            {
                "chunk_id": item.chunk_id,
                "page_number": item.page_number,
                "section": item.section,
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        evidence_lines = "\n".join(
            f"- Page {item.page_number}: {item.text[:180]}"
            for item in evidence
        )
        notes = "\n".join(
            f"- {item}" for item in turn.evidence_notes
        ) or "- None stated"
        markdown = (
            f"# {paper.title} Guided Reading Note\n\n"
            f"## Learning Summary\n\n{turn.learning_summary}\n\n"
            f"## Final Feedback\n\n{turn.feedback}\n\n"
            f"## Evidence Notes\n\n{notes}\n\n"
            f"## Source Evidence\n\n{evidence_lines}\n"
        )
        return ArtifactRepository(self.db).create_artifact(
            project_id=paper.project_id,
            artifact_type="guided_reading_note",
            title=f"{paper.title} guided reading note",
            content={
                **turn.model_dump(),
                "paper_id": paper.id,
                "evidence": evidence_content,
            },
            markdown=markdown,
        )
