import asyncio
import re
from typing import List, Protocol

from langchain_community.retrievers import ArxivRetriever
from langchain_core.documents import Document

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


def documents_to_arxiv_papers(
    documents: List[Document],
) -> List[ArxivPaper]:
    by_id = {}
    for document in documents:
        metadata = document.metadata
        entry_url = str(
            metadata.get("Entry ID")
            or metadata.get("entry_id")
            or ""
        )
        arxiv_id = normalize_arxiv_id(entry_url)
        if not arxiv_id:
            continue
        authors = [
            author.strip()
            for author in str(metadata.get("Authors", "")).split(",")
            if author.strip()
        ]
        by_id[arxiv_id] = ArxivPaper(
            arxiv_id=arxiv_id,
            title=str(metadata.get("Title", "")).strip(),
            authors=authors,
            abstract=document.page_content.strip(),
            published=str(metadata.get("Published", "")),
            categories=list(metadata.get("categories", [])),
            entry_url=entry_url or f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        )
    return list(by_id.values())


class LangChainArxivSearchProvider:
    def __init__(self, max_results: int = 20) -> None:
        self._retriever = ArxivRetriever(
            top_k_results=max_results,
            load_max_docs=max_results,
            get_full_documents=False,
        )

    async def search(self, query: str) -> List[ArxivPaper]:
        documents = await asyncio.to_thread(self._retriever.invoke, query)
        return documents_to_arxiv_papers(documents)
