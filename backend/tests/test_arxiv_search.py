from langchain_core.documents import Document

from research_agent.services.arxiv_search import (
    documents_to_arxiv_papers,
    normalize_arxiv_id,
)


def test_normalize_arxiv_id_removes_version() -> None:
    assert normalize_arxiv_id(
        "https://arxiv.org/abs/2305.05665v2"
    ) == "2305.05665"


def test_documents_map_and_deduplicate_versions() -> None:
    documents = [
        Document(
            page_content="First abstract",
            metadata={
                "Entry ID": "https://arxiv.org/abs/2305.05665v1",
                "Published": "2023-05-09",
                "Title": "First title",
                "Authors": "A. Author, B. Author",
            },
        ),
        Document(
            page_content="Revised abstract",
            metadata={
                "Entry ID": "https://arxiv.org/abs/2305.05665v2",
                "Published": "2023-05-10",
                "Title": "Revised title",
                "Authors": "A. Author, B. Author",
            },
        ),
    ]

    papers = documents_to_arxiv_papers(documents)

    assert len(papers) == 1
    assert papers[0].arxiv_id == "2305.05665"
    assert papers[0].title == "Revised title"
    assert papers[0].authors == ["A. Author", "B. Author"]
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2305.05665"
