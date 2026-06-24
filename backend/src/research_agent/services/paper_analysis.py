from dataclasses import dataclass
import json
import time
from typing import List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact, Paper
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.paper_chunks import EvidenceResult, PaperChunkRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway
from research_agent.services.structured_output import validate_structured


class LiteratureCard(BaseModel):
    research_topic: str = ""
    research_question: str = ""
    method: str = ""
    contribution: str = ""
    risks: List[str] = Field(default_factory=list)


class ComparisonFinding(BaseModel):
    dimension: str = ""
    summary: str = ""
    evidence_notes: List[str] = Field(default_factory=list)


class PaperComparison(BaseModel):
    overview: str = ""
    findings: List[ComparisonFinding] = Field(default_factory=list)
    transferable_insights: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PaperAnalysisResult:
    artifact: Artifact
    evidence: List[EvidenceResult]

    @property
    def evidence_pages(self) -> List[int]:
        pages = []
        for item in self.evidence:
            if item.page_number not in pages:
                pages.append(item.page_number)
        return pages


@dataclass(frozen=True)
class PaperComparisonResult:
    artifact: Artifact
    evidence_by_paper: dict[str, List[EvidenceResult]]

    @property
    def evidence_pages(self) -> dict[str, List[int]]:
        pages_by_paper = {}
        for paper_id, evidence in self.evidence_by_paper.items():
            pages = []
            for item in evidence:
                if item.page_number not in pages:
                    pages.append(item.page_number)
            pages_by_paper[paper_id] = pages
        return pages_by_paper


class PaperAnalysisService:
    METHOD_KEYWORDS = (
        "method",
        "methodology",
        "experiment",
        "evaluation",
        "dataset",
        "data",
        "model",
        "方法",
        "实验",
        "数据",
        "模型",
        "评价",
        "评估",
    )

    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.model_gateway = model_gateway

    async def quick_analyze(self, paper_id: str) -> PaperAnalysisResult:
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            raise LookupError("paper not found")

        candidates = PaperChunkRepository(self.db).list_for_paper(paper_id, limit=40)
        evidence = self._select_evidence(candidates, limit=8)
        card = await self._build_card(paper.title, evidence)
        markdown = self._to_markdown(paper.title, card, evidence)
        content = card.model_dump()
        content["evidence"] = [
            {
                "chunk_id": item.chunk_id,
                "page_number": item.page_number,
                "section": item.section,
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        artifact = ArtifactRepository(self.db).create_artifact(
            project_id=paper.project_id,
            artifact_type="literature_card",
            title=f"{paper.title} literature card",
            content=content,
            markdown=markdown,
        )
        return PaperAnalysisResult(artifact=artifact, evidence=evidence)

    async def compare_papers(self, paper_ids: List[str]) -> PaperComparisonResult:
        if not 2 <= len(paper_ids) <= 3:
            raise ValueError("paper comparison requires 2 to 3 papers")
        if len(set(paper_ids)) != len(paper_ids):
            raise ValueError("paper IDs must be unique")

        papers = []
        for paper_id in paper_ids:
            paper = self.db.get(Paper, paper_id)
            if paper is None:
                raise LookupError("paper not found")
            papers.append(paper)

        project_ids = {paper.project_id for paper in papers}
        if len(project_ids) != 1:
            raise ValueError("papers must belong to the same project")

        chunk_repo = PaperChunkRepository(self.db)
        evidence_by_paper = {
            paper.id: self._select_evidence(
                chunk_repo.list_for_paper(paper.id, limit=40),
                limit=6,
            )
            for paper in papers
        }
        comparison = await self._build_comparison(papers, evidence_by_paper)
        markdown = self._comparison_to_markdown(
            papers,
            comparison,
            evidence_by_paper,
        )
        content = comparison.model_dump()
        content["papers"] = [
            {
                "paper_id": paper.id,
                "title": paper.title,
            }
            for paper in papers
        ]
        content["evidence"] = {
            paper_id: [
                {
                    "chunk_id": item.chunk_id,
                    "page_number": item.page_number,
                    "section": item.section,
                    "is_ocr": item.is_ocr,
                }
                for item in evidence
            ]
            for paper_id, evidence in evidence_by_paper.items()
        }
        artifact = ArtifactRepository(self.db).create_artifact(
            project_id=papers[0].project_id,
            artifact_type="paper_comparison",
            title="Paper comparison",
            content=content,
            markdown=markdown,
        )
        return PaperComparisonResult(
            artifact=artifact,
            evidence_by_paper=evidence_by_paper,
        )

    def _select_evidence(
        self,
        candidates: List[EvidenceResult],
        limit: int,
    ) -> List[EvidenceResult]:
        if not candidates:
            return []

        first_page = min(item.page_number for item in candidates)
        selected = [
            item for item in candidates
            if item.page_number == first_page
        ]
        selected.extend(
            item for item in candidates
            if self._is_method_related(item)
        )

        deduped = []
        seen = set()
        for item in selected:
            if item.chunk_id in seen:
                continue
            deduped.append(item)
            seen.add(item.chunk_id)
            if len(deduped) == limit:
                return deduped
        return deduped

    def _is_method_related(self, item: EvidenceResult) -> bool:
        haystack = f"{item.section}\n{item.text}".lower()
        return any(keyword.lower() in haystack for keyword in self.METHOD_KEYWORDS)

    async def _build_card(
        self,
        title: str,
        evidence: List[EvidenceResult],
    ) -> LiteratureCard:
        payload = [
            {
                "chunk_id": item.chunk_id,
                "page": item.page_number,
                "text": item.text[:1200],
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        prompt = (
            "Create an evidence-bound literature card from the supplied paper "
            "chunks. Use only the evidence. If a field is not supported, leave "
            "it empty. Return JSON only with keys: research_topic, "
            "research_question, method, contribution, risks.\n"
            f"Title: {title}\n"
            f"Evidence: {json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = LiteratureCard(
            risks=["Model output could not be parsed; manual review is required."],
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=LiteratureCard.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "paper_quick_analysis",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "paper_quick_analysis",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    async def _build_comparison(
        self,
        papers: List[Paper],
        evidence_by_paper: dict[str, List[EvidenceResult]],
    ) -> PaperComparison:
        payload = [
            {
                "paper_id": paper.id,
                "title": paper.title,
                "evidence": [
                    {
                        "chunk_id": item.chunk_id,
                        "page": item.page_number,
                        "text": item.text[:1000],
                        "is_ocr": item.is_ocr,
                    }
                    for item in evidence_by_paper[paper.id]
                ],
            }
            for paper in papers
        ]
        prompt = (
            "Create an evidence-bound paper comparison from the supplied paper "
            "chunks. Use only the evidence. Compare research question, method, "
            "data, and contribution when supported. Return JSON only with keys: "
            "overview, findings, transferable_insights, risks. findings must be "
            "a list of objects with dimension, summary, evidence_notes.\n"
            f"Papers: {json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = PaperComparison(
            risks=["Model output could not be parsed; manual review is required."],
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=PaperComparison.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "paper_comparison",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "paper_comparison",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    @staticmethod
    def _to_markdown(
        title: str,
        card: LiteratureCard,
        evidence: List[EvidenceResult],
    ) -> str:
        risks = "\n".join(f"- {risk}" for risk in card.risks) or "- None stated"
        evidence_lines = "\n".join(
            f"- Page {item.page_number}: {item.text[:160]}"
            for item in evidence
        ) or "- No stored evidence chunks were available."
        return (
            f"# {title} Literature Card\n\n"
            f"## Research Topic\n\n{card.research_topic}\n\n"
            f"## Research Question\n\n{card.research_question}\n\n"
            f"## Method\n\n{card.method}\n\n"
            f"## Contribution\n\n{card.contribution}\n\n"
            f"## Risks\n\n{risks}\n\n"
            f"## Evidence\n\n{evidence_lines}\n"
        )

    @staticmethod
    def _comparison_to_markdown(
        papers: List[Paper],
        comparison: PaperComparison,
        evidence_by_paper: dict[str, List[EvidenceResult]],
    ) -> str:
        paper_lines = "\n".join(f"- {paper.title}" for paper in papers)
        finding_lines = "\n".join(
            f"### {item.dimension}\n\n{item.summary}\n"
            for item in comparison.findings
        ) or "No validated comparison findings were produced.\n"
        insights = (
            "\n".join(f"- {item}" for item in comparison.transferable_insights)
            or "- None stated"
        )
        risks = "\n".join(f"- {item}" for item in comparison.risks) or "- None stated"
        evidence_lines = []
        for paper in papers:
            evidence_lines.append(f"### {paper.title}")
            paper_evidence = evidence_by_paper.get(paper.id, [])
            if not paper_evidence:
                evidence_lines.append("- No stored evidence chunks were available.")
                continue
            evidence_lines.extend(
                f"- Page {item.page_number}: {item.text[:140]}"
                for item in paper_evidence
            )
        return (
            "# Paper Comparison\n\n"
            f"## Papers\n\n{paper_lines}\n\n"
            f"## Overview\n\n{comparison.overview}\n\n"
            f"## Findings\n\n{finding_lines}\n"
            f"## Transferable Insights\n\n{insights}\n\n"
            f"## Risks\n\n{risks}\n\n"
            f"## Evidence\n\n{chr(10).join(evidence_lines)}\n"
        )
