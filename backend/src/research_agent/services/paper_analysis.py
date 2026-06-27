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
from research_agent.services.model_gateway import ModelGateway, collect_chat


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
    COMPARISON_DIMENSIONS = {
        "研究问题": (
            "abstract",
            "introduction",
            "problem",
            "objective",
            "研究问题",
            "目标",
            "摘要",
            "引言",
        ),
        "方法与数据": METHOD_KEYWORDS,
        "实验与结果": (
            "result",
            "finding",
            "performance",
            "baseline",
            "结果",
            "发现",
            "性能",
            "对比",
        ),
        "贡献与局限": (
            "contribution",
            "conclusion",
            "limitation",
            "future",
            "贡献",
            "结论",
            "局限",
            "不足",
            "未来",
        ),
    }

    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.model_gateway = model_gateway

    async def quick_analyze(self, paper_id: str) -> PaperAnalysisResult:
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            raise LookupError("paper not found")

        candidates = PaperChunkRepository(self.db).list_for_paper(paper_id, limit=40)
        evidence = self._select_evidence(candidates, limit=8)
        markdown = (
            await self._build_quick_report(paper.title, evidence)
            if evidence
            else self._quick_report_fallback(paper.title, evidence)
        )
        content = {
            "title": paper.title,
            "report": markdown,
            "paper_id": paper.id,
        }
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
            title=f"论文解读：{paper.title}",
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
            if not paper.favorited and not paper.arxiv_id.startswith("upload:"):
                raise ValueError("paper must be favorited before comparison")
            papers.append(paper)

        project_ids = {paper.project_id for paper in papers}
        if len(project_ids) != 1:
            raise ValueError("papers must belong to the same project")

        chunk_repo = PaperChunkRepository(self.db)
        evidence_by_paper = {
            paper.id: self._select_evidence(
                chunk_repo.list_for_paper(paper.id, limit=80),
                limit=10,
            )
            for paper in papers
        }
        has_evidence = any(evidence_by_paper.values())
        markdown = (
            await self._build_comparison_report(papers, evidence_by_paper)
            if has_evidence
            else self._comparison_report_fallback(papers, evidence_by_paper)
        )
        content = {"report": markdown}
        content["papers"] = [
            {"paper_id": p.id, "title": p.title}
            for p in papers
        ]
        content["evidence"] = {}
        for pid, ev_list in evidence_by_paper.items():
            content["evidence"][pid] = [
                {
                    "chunk_id": item.chunk_id,
                    "page_number": item.page_number,
                    "section": item.section,
                    "is_ocr": item.is_ocr,
                }
                for item in ev_list
            ]
        artifact = ArtifactRepository(self.db).create_artifact(
            project_id=papers[0].project_id,
            artifact_type="paper_comparison",
            title=f"论文对比：{' / '.join(p.title[:18] for p in papers)}",
            content=content,
            markdown=markdown,
        )
        return PaperComparisonResult(
            artifact=artifact,
            evidence_by_paper=evidence_by_paper,
        )

    async def _build_quick_report(
        self,
        title: str,
        evidence: List[EvidenceResult],
    ) -> str:
        payload = [
            {
                "page": item.page_number,
                "section": item.section,
                "text": item.text[:1200],
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        prompt = (
            "你是一位严谨的学术论文评审专家。请基于这篇论文，为研究者生成一份完整全面的论文解读。用中文回答。\n"
            "请直接输出报告正文，不要写称呼、寒暄、道歉或关于提示词/原文缺失的说明。\n"
            f"\n论文标题：{title}\n"
            f"\n论文原文：{json.dumps(payload, ensure_ascii=False)}"
        )
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.model_gateway,
                [{"role": "user", "content": prompt}],
            )
            record_model_call(
                self.db,
                "paper_quick_analysis",
                self.model_gateway.model_name,
                started,
                0,
                True,
            )
            return response.strip() or self._quick_report_fallback(title, evidence)
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

    async def _build_comparison_report(
        self,
        papers: List[Paper],
        evidence_by_paper: dict[str, List[EvidenceResult]],
    ) -> str:
        payload = [
            {
                "title": paper.title,
                "pages": [
                    {
                        "page": item.page_number,
                        "section": item.section,
                        "text": item.text[:1000],
                        "is_ocr": item.is_ocr,
                    }
                    for item in evidence_by_paper[paper.id]
                ],
            }
            for paper in papers
        ]
        prompt = (
            "你是一位严谨的学术论文评审专家。请基于以下多篇论文的原文生成中文对比报告。\n"
            "请直接输出报告正文，不要写称呼、寒暄、道歉或关于提示词/原文缺失的说明。\n"
            f"\n论文原文：{json.dumps(payload, ensure_ascii=False)}"
        )
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.model_gateway,
                [{"role": "user", "content": prompt}],
            )
            record_model_call(
                self.db,
                "paper_comparison",
                self.model_gateway.model_name,
                started,
                0,
                True,
            )
            if response.strip():
                return response.strip()
            return self._comparison_report_fallback(papers, evidence_by_paper)
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

    def _select_evidence(
        self,
        candidates: List[EvidenceResult],
        limit: int,
    ) -> List[EvidenceResult]:
        if not candidates:
            return []

        first_page = min(item.page_number for item in candidates)
        selected = [item for item in candidates if item.page_number == first_page]
        for keywords in self.COMPARISON_DIMENSIONS.values():
            selected.extend(
                item for item in candidates
                if self._matches_keywords(item, keywords)
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
        return self._matches_keywords(item, self.METHOD_KEYWORDS)

    @staticmethod
    def _matches_keywords(item: EvidenceResult, keywords) -> bool:
        haystack = f"{item.section}\n{item.text}".lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    @staticmethod
    def _quick_report_fallback(
        title: str,
        evidence: List[EvidenceResult],
    ) -> str:
        evidence_lines = "\n".join(
            f"- 第 {item.page_number} 页：{item.text[:180]}"
            for item in evidence
        ) or "- 暂无已解析正文。"
        return (
            f"# {title} 论文解读\n\n"
            "当前没有可供模型精读的完整正文；以下为系统根据已解析页面整理的阅读入口。\n\n"
            f"## 原文摘录\n\n{evidence_lines}\n"
        )

    def _comparison_report_fallback(
        self,
        papers: List[Paper],
        evidence_by_paper: dict[str, List[EvidenceResult]],
    ) -> str:
        paper_lines = "\n".join(f"- {paper.title}" for paper in papers)
        evidence_lines = []
        for dimension, keywords in self.COMPARISON_DIMENSIONS.items():
            evidence_lines.append(f"## {dimension}")
            for paper in papers:
                evidence = [
                    item for item in evidence_by_paper.get(paper.id, [])
                    if self._matches_keywords(item, keywords)
                ] or evidence_by_paper.get(paper.id, [])[:2]
                if evidence:
                    item = evidence[0]
                    evidence_lines.append(
                        f"- {paper.title}，第 {item.page_number} 页："
                        f"{item.text[:180]}"
                    )
            if evidence_lines[-1] == f"## {dimension}":
                evidence_lines.append("- 暂无可用正文摘录。")
        return (
            "# 论文对比报告\n\n"
            f"## 对比论文\n\n{paper_lines}\n\n"
            "当前没有可供模型对比的完整正文；以下为系统根据已解析页面整理的对比入口。\n\n"
            + "\n\n".join(evidence_lines)
            + "\n"
        )
