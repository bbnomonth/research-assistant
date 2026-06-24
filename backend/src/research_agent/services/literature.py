import json
import re
from typing import List

from pydantic import TypeAdapter, ValidationError

from research_agent.schemas.literature import (
    LiteratureDiscoveryResult,
    LiteratureQuery,
    RecommendationItem,
    RecommendedPaper,
)
from research_agent.services.arxiv_search import ArxivSearchProvider
from research_agent.services.model_gateway import ModelGateway, collect_chat


JSON_FENCE = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json(text: str):
    stripped = text.strip()
    match = JSON_FENCE.search(stripped)
    if match:
        stripped = match.group(1).strip()
    return json.loads(stripped)


class LiteratureDiscoveryService:
    def __init__(
        self,
        model_gateway: ModelGateway,
        arxiv_provider: ArxivSearchProvider,
    ) -> None:
        self.model_gateway = model_gateway
        self.arxiv_provider = arxiv_provider

    async def discover(self, topic: str) -> LiteratureDiscoveryResult:
        query = await self._generate_query(topic)
        candidates = await self.arxiv_provider.search(query)
        recommendations = await self._recommend(topic, candidates)
        return LiteratureDiscoveryResult(
            query=query,
            candidates=candidates,
            recommendations=recommendations,
        )

    async def _generate_query(self, topic: str) -> str:
        prompt = (
            "把用户研究主题转换为简洁的英文 arXiv 检索式。"
            "只输出 JSON，格式为 "
            '{"english_query":"..."}。'
            f"\n用户主题：{topic}"
        )
        response = await collect_chat(
            self.model_gateway,
            [{"role": "user", "content": prompt}],
        )
        try:
            return LiteratureQuery.model_validate(
                extract_json(response)
            ).english_query.strip()
        except (ValueError, ValidationError):
            return topic

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
            "只能使用提供的 arxiv_id。"
            "只输出 JSON 数组，每项包含 arxiv_id、reason、"
            "purpose_labels。"
            f"\n用户主题：{topic}"
            f"\n候选文献：{json.dumps(candidate_payload, ensure_ascii=False)}"
        )
        response = await collect_chat(
            self.model_gateway,
            [{"role": "user", "content": prompt}],
        )
        try:
            items = TypeAdapter(
                List[RecommendationItem]
            ).validate_python(extract_json(response))
        except (ValueError, ValidationError):
            items = []

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
