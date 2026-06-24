import asyncio

from research_agent.schemas.literature import ArxivPaper
from research_agent.services.literature import LiteratureDiscoveryService


def make_paper(index: int) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=f"2401.0000{index}",
        title=f"Paper {index}",
        authors=[f"Author {index}"],
        abstract=f"Abstract {index}",
        published="2024-01-01",
        categories=["cs.AI"],
        entry_url=f"https://arxiv.org/abs/2401.0000{index}",
        pdf_url=f"https://arxiv.org/pdf/2401.0000{index}",
    )


class FakeArxivProvider:
    async def search(self, query: str):
        assert query == '"vehicle routing" AND "machine learning"'
        return [make_paper(index) for index in range(1, 7)]


class ScriptedGateway:
    model_name = "fake"

    def __init__(self) -> None:
        self.responses = [
            ['{"english_query":"\\"vehicle routing\\" AND \\"machine learning\\""}'],
            [
                """```json
                [
                  {
                    "arxiv_id": "2401.00001",
                    "reason": "方法相关",
                    "purpose_labels": ["方法相似"]
                  },
                  {
                    "arxiv_id": "not-real",
                    "reason": "无效",
                    "purpose_labels": []
                  }
                ]
                ```"""
            ],
        ]

    async def stream_chat(self, messages):
        del messages
        for token in self.responses.pop(0):
            yield token


def test_literature_service_filters_ids_and_fills_five_results() -> None:
    async def run():
        service = LiteratureDiscoveryService(
            model_gateway=ScriptedGateway(),
            arxiv_provider=FakeArxivProvider(),
        )
        return await service.discover("机器学习在车辆路径优化中的应用")

    result = asyncio.run(run())

    assert result.query == '"vehicle routing" AND "machine learning"'
    assert len(result.candidates) == 6
    assert len(result.recommendations) == 5
    assert result.recommendations[0].paper.arxiv_id == "2401.00001"
    assert all(
        recommendation.paper.arxiv_id != "not-real"
        for recommendation in result.recommendations
    )
