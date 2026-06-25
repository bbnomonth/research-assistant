import json
import time
from typing import List, Optional

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.schemas.literature import (
    LiteratureDiscoveryResult,
    LiteratureQuery,
    RecommendationItem,
    RecommendedPaper,
)
from research_agent.services.arxiv_search import ArxivSearchProvider
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway
from research_agent.services.structured_output import validate_structured


class LiteratureDiscoveryService:
    def __init__(
        self,
        model_gateway: ModelGateway,
        arxiv_provider: ArxivSearchProvider,
        db: Optional[Session] = None,
        project_id: Optional[str] = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.arxiv_provider = arxiv_provider
        self.db = db
        self.project_id = project_id

    async def discover(self, topic: str) -> LiteratureDiscoveryResult:
        query = await self._generate_query(topic)
        candidates = await self.arxiv_provider.search(query)
        recommendations = await self._recommend(topic, candidates)
        return LiteratureDiscoveryResult(
            query=query,
            candidates=candidates,
            recommendations=recommendations,
        )

    async def discover_with_artifact(
        self,
        topic: str,
    ) -> tuple[LiteratureDiscoveryResult, Optional[Artifact]]:
        """Discover papers and generate a structured literature card artifact."""
        result = await self.discover(topic)
        artifact = None
        if self.db is not None and self.project_id is not None and result.recommendations:
            artifact = await self._generate_card_artifact(topic, result)
        return result, artifact

    async def _generate_query(self, topic: str) -> str:
        prompt = (
            "把用户研究主题转换为简洁的英文检索式。"
            "只输出 JSON，格式为 "
            '{"english_query":"..."}。'
            f"\n用户主题：{topic}"
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=LiteratureQuery.model_validate,
                fallback=LiteratureQuery(english_query=topic),
            )
            record_model_call(
                self.db,
                "literature_query",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value.english_query.strip()
        except Exception as exc:
            record_model_call(
                self.db,
                "literature_query",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    async def _recommend(
        self,
        topic: str,
        candidates,
    ) -> List[RecommendedPaper]:
        if not candidates:
            return []

        candidate_payload = [
            {
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
                "abstract": paper.abstract[:800],
            }
            for paper in candidates
        ]
        prompt = (
            "从候选文献中推荐最相关的 5 到 10 篇。"
            "只能使用提供的论文 ID。"
            "只输出 JSON 数组，每项包含 arxiv_id、reason、"
            "purpose_labels。"
            f"\n用户主题：{topic}"
            f"\n候选文献：{json.dumps(candidate_payload, ensure_ascii=False)}"
        )
        adapter = TypeAdapter(List[RecommendationItem])
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=adapter.validate_python,
                fallback=[],
            )
            record_model_call(
                self.db,
                "literature_recommendation",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            items = result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "literature_recommendation",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

        candidate_by_id = {
            paper.arxiv_id: paper
            for paper in candidates
        }
        selected = []
        used = set()
        for item in items:
            paper = candidate_by_id.get(item.arxiv_id)
            if paper is None or item.arxiv_id in used:
                continue
            selected.append(
                RecommendedPaper(
                    paper=paper,
                    reason=item.reason,
                    purpose_labels=item.purpose_labels,
                )
            )
            used.add(item.arxiv_id)
            if len(selected) == 10:
                return selected

        target = min(5, len(candidates))
        for paper in candidates:
            if len(selected) >= target:
                break
            if paper.arxiv_id in used:
                continue
            selected.append(
                RecommendedPaper(
                    paper=paper,
                    reason="该文献与当前检索主题相关，建议进一步查看摘要。",
                    purpose_labels=["相关文献"],
                )
            )
            used.add(paper.arxiv_id)
        return selected

    async def _generate_card_artifact(
        self,
        topic: str,
        result: LiteratureDiscoveryResult,
    ) -> Optional[Artifact]:
        """Generate a structured literature card artifact from discovered papers."""
        if not result.recommendations or not self.db or not self.project_id:
            return None

        from research_agent.services.paper_analysis import LiteratureCard

        payload = [
            {
                "arxiv_id": r.paper.arxiv_id,
                "title": r.paper.title,
                "abstract": r.paper.abstract[:600],
                "reason": r.reason,
            }
            for r in result.recommendations[:5]
        ]
        prompt = (
            "You are a research advisor. Based on the user's research topic and recommended papers, "
            "generate a concise literature card (文献卡片) in Chinese.\n"
            "Use the supplied paper information only. Return JSON only with keys: "
            "research_topic, research_question, method, contribution, risks.\n"
            "- research_topic: 研究主题（3-10字）\n"
            "- research_question: 核心研究问题（1-2句话）\n"
            "- method: 主要研究方法（1-3句话）\n"
            "- contribution: 主要贡献和创新点（1-3句话）\n"
            "- risks: 研究局限或风险（列出2-3条）\n"
            f"\nUser topic: {topic}\n"
            f"\nRecommended papers: {json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = LiteratureCard(
            research_topic=topic[:20],
            research_question="基于检索结果的主题分析",
            method="综合多篇文献的方法论概述",
            contribution="详见推荐文献原文",
            risks=["文献数量有限，建议进一步扩大检索范围"],
        )
        started = time.perf_counter()
        try:
            cls_result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=LiteratureCard.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "literature_card",
                self.model_gateway.model_name,
                started,
                cls_result.retries,
                True,
            )
            card = cls_result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "literature_card",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            card = fallback

        evidence_lines = "\n".join(
            f"- {r.paper.title} ({r.paper.arxiv_id})：{r.reason}"
            for r in result.recommendations[:5]
        )
        markdown = (
            f"# 文献卡片\n\n"
            f"## 研究主题\n\n{card.research_topic}\n\n"
            f"## 核心研究问题\n\n{card.research_question}\n\n"
            f"## 主要研究方法\n\n{card.method}\n\n"
            f"## 主要贡献\n\n{card.contribution}\n\n"
            f"## 研究风险与局限\n\n"
            + "\n".join(f"- {r}" for r in card.risks)
            + f"\n\n## 推荐文献\n\n{evidence_lines}\n"
        )
        content = card.model_dump()
        content["query"] = result.query
        content["recommendations"] = [
            {
                "arxiv_id": r.paper.arxiv_id,
                "title": r.paper.title,
                "reason": r.reason,
            }
            for r in result.recommendations
        ]
        return ArtifactRepository(self.db).create_artifact(
            project_id=self.project_id,
            artifact_type="literature_card",
            title=f"文献卡片：{card.research_topic or topic[:20]}",
            content=content,
            markdown=markdown,
        )


class LocalLiteratureDiscoveryService:
    """Model-free paper discovery for privacy-local operation."""

    def __init__(self, arxiv_provider: ArxivSearchProvider) -> None:
        self.arxiv_provider = arxiv_provider

    async def discover(self, topic: str) -> LiteratureDiscoveryResult:
        query = topic.strip()
        candidates = await self.arxiv_provider.search(query)
        recommendations = [
            RecommendedPaper(
                paper=paper,
                reason="本地模式下按检索顺序推荐，请人工核对摘要。",
                purpose_labels=["本地检索"],
            )
            for paper in candidates[:10]
        ]
        return LiteratureDiscoveryResult(
            query=query,
            candidates=candidates,
            recommendations=recommendations,
        )
