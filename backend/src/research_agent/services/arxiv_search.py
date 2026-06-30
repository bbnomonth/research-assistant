import asyncio
import re
from typing import List, Protocol

import arxiv

from research_agent.schemas.literature import ArxivPaper


ARXIV_ID_PATTERN = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?([^/]+?)(?:v\d+)?(?:\.pdf)?$",
    re.IGNORECASE,
)


class ArxivSearchProvider(Protocol):
    async def search(self, query: str) -> List[ArxivPaper]:
        pass


def normalize_arxiv_id(value: str) -> str:
    candidate = value.strip().rstrip("/")
    match = ARXIV_ID_PATTERN.search(candidate)
    if not match:
        return candidate
    return match.group(1)


def arxiv_results_to_papers(results) -> List[ArxivPaper]:
    by_id = {}
    for result in results:
        entry_url = str(getattr(result, "entry_id", "") or "")
        arxiv_id = normalize_arxiv_id(entry_url)
        if not arxiv_id:
            get_short_id = getattr(result, "get_short_id", None)
            if callable(get_short_id):
                arxiv_id = normalize_arxiv_id(str(get_short_id()))
        if not arxiv_id:
            continue
        authors = [_author_name(author) for author in getattr(result, "authors", [])]
        authors = [author for author in authors if author]
        published = _published_date(getattr(result, "published", ""))
        by_id[arxiv_id] = ArxivPaper(
            arxiv_id=arxiv_id,
            title=str(getattr(result, "title", "") or "").strip(),
            authors=authors,
            abstract=str(getattr(result, "summary", "") or "").strip(),
            published=published,
            categories=list(getattr(result, "categories", []) or []),
            entry_url=entry_url or f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        )
    return list(by_id.values())


def _author_name(author) -> str:
    return str(getattr(author, "name", author) or "").strip()


def _published_date(value) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value or "").strip()


class ArxivClientSearchProvider:
    def __init__(self, max_results: int = 20, client=None) -> None:
        self.max_results = max_results
        self._client = client or arxiv.Client(
            page_size=max_results,
            delay_seconds=3.0,
            num_retries=3,
        )

    async def search(self, query: str) -> List[ArxivPaper]:
        search = arxiv.Search(
            query=query,
            max_results=self.max_results,
            sort_by=arxiv.SortCriterion.Relevance,
            sort_order=arxiv.SortOrder.Descending,
        )
        results = await asyncio.to_thread(lambda: list(self._client.results(search)))
        return arxiv_results_to_papers(results)
