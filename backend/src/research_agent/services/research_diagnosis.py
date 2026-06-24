from dataclasses import dataclass
import json
import time
from typing import List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.paper_chunks import EvidenceResult, PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway
from research_agent.services.structured_output import validate_structured


class ResearchDiagnosis(BaseModel):
    topic_summary: str = ""
    evidence_supported_judgements: List[str] = Field(default_factory=list)
    reasonable_inferences: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    next_questions: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class DiagnosisResult:
    artifact: Artifact
    evidence: dict[str, List[EvidenceResult]]

    @property
    def evidence_pages(self) -> dict[str, List[int]]:
        pages_by_paper = {}
        for paper_id, items in self.evidence.items():
            pages = []
            for item in items:
                if item.page_number not in pages:
                    pages.append(item.page_number)
            pages_by_paper[paper_id] = pages
        return pages_by_paper


class ResearchDiagnosisService:
    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.model_gateway = model_gateway

    async def diagnose(self, project_id: str, user_input: str) -> DiagnosisResult:
        papers = PaperRepository(self.db).list_for_project(project_id, limit=5)
        chunk_repo = PaperChunkRepository(self.db)
        evidence = {
            paper.id: chunk_repo.list_for_paper(paper.id, limit=4)
            for paper in papers
        }
        diagnosis = await self._build_diagnosis(user_input, papers, evidence)
        markdown = self._to_markdown(diagnosis, papers, evidence)
        content = diagnosis.model_dump()
        content["evidence"] = {
            paper_id: [
                {
                    "chunk_id": item.chunk_id,
                    "page_number": item.page_number,
                    "section": item.section,
                    "is_ocr": item.is_ocr,
                }
                for item in items
            ]
            for paper_id, items in evidence.items()
        }
        artifact = ArtifactRepository(self.db).create_artifact(
            project_id=project_id,
            artifact_type="research_diagnosis",
            title="Research diagnosis",
            content=content,
            markdown=markdown,
        )
        return DiagnosisResult(artifact=artifact, evidence=evidence)

    async def _build_diagnosis(
        self,
        user_input: str,
        papers,
        evidence: dict[str, List[EvidenceResult]],
    ) -> ResearchDiagnosis:
        payload = [
            {
                "paper_id": paper.id,
                "title": paper.title,
                "evidence": [
                    {
                        "chunk_id": item.chunk_id,
                        "page": item.page_number,
                        "text": item.text[:900],
                        "is_ocr": item.is_ocr,
                    }
                    for item in evidence[paper.id]
                ],
            }
            for paper in papers
        ]
        prompt = (
            "Create a research-design diagnosis for a novice researcher. "
            "Separate evidence-supported judgements from reasonable inferences. "
            "Use supplied paper evidence when available; otherwise state evidence "
            "limitations. Return JSON only with keys: topic_summary, "
            "evidence_supported_judgements, reasonable_inferences, gaps, risks, "
            "next_questions.\n"
            f"User material: {user_input}\n"
            f"Project paper evidence: {json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = ResearchDiagnosis(
            topic_summary=user_input,
            gaps=["Model output could not be parsed; manual review is required."],
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=ResearchDiagnosis.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "research_diagnosis",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "research_diagnosis",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    @staticmethod
    def _to_markdown(diagnosis: ResearchDiagnosis, papers, evidence) -> str:
        def bullets(items: List[str]) -> str:
            return "\n".join(f"- {item}" for item in items) or "- None stated"

        evidence_lines = []
        for paper in papers:
            evidence_lines.append(f"### {paper.title}")
            paper_evidence = evidence.get(paper.id, [])
            if not paper_evidence:
                evidence_lines.append("- No stored evidence chunks were available.")
                continue
            evidence_lines.extend(
                f"- Page {item.page_number}: {item.text[:140]}"
                for item in paper_evidence
            )
        if not evidence_lines:
            evidence_lines.append("- No project papers were available.")

        return (
            "# Research Diagnosis\n\n"
            f"## Topic Summary\n\n{diagnosis.topic_summary}\n\n"
            "## Evidence-Supported Judgements\n\n"
            f"{bullets(diagnosis.evidence_supported_judgements)}\n\n"
            "## Reasonable Inferences\n\n"
            f"{bullets(diagnosis.reasonable_inferences)}\n\n"
            f"## Gaps\n\n{bullets(diagnosis.gaps)}\n\n"
            f"## Risks\n\n{bullets(diagnosis.risks)}\n\n"
            f"## Next Questions\n\n{bullets(diagnosis.next_questions)}\n\n"
            f"## Evidence\n\n{chr(10).join(evidence_lines)}\n"
        )
