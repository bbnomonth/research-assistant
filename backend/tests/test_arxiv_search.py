import asyncio
from datetime import datetime, timezone

from research_agent.services.arxiv_search import (
    ArxivClientSearchProvider,
    normalize_arxiv_id,
)


def test_normalize_arxiv_id_removes_version() -> None:
    assert normalize_arxiv_id(
        "https://arxiv.org/abs/2305.05665v2"
    ) == "2305.05665"


class FakeAuthor:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeResult:
    def __init__(self, version: int, title: str, summary: str) -> None:
        self.entry_id = f"https://arxiv.org/abs/2305.05665v{version}"
        self.title = title
        self.summary = summary
        self.authors = [FakeAuthor("A. Author"), FakeAuthor("B. Author")]
        self.published = datetime(2023, 5, 9 + version, tzinfo=timezone.utc)
        self.categories = ["cs.AI"]
        self.pdf_url = f"https://arxiv.org/pdf/2305.05665v{version}"


class FakeArxivClient:
    def __init__(self) -> None:
        self.searches = []

    def results(self, search):
        self.searches.append(search)
        return iter(
            [
                FakeResult(1, "First title", "First abstract"),
                FakeResult(2, "Revised title", "Revised abstract"),
            ]
        )


def test_provider_uses_arxiv_client_and_deduplicates_versions() -> None:
    client = FakeArxivClient()
    provider = ArxivClientSearchProvider(max_results=20, client=client)

    papers = asyncio.run(provider.search("vehicle routing"))

    assert len(papers) == 1
    assert papers[0].arxiv_id == "2305.05665"
    assert papers[0].title == "Revised title"
    assert papers[0].authors == ["A. Author", "B. Author"]
    assert papers[0].abstract == "Revised abstract"
    assert papers[0].published == "2023-05-11"
    assert papers[0].categories == ["cs.AI"]
    assert papers[0].entry_url == "https://arxiv.org/abs/2305.05665v2"
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2305.05665"
    assert client.searches[0].query == "vehicle routing"
