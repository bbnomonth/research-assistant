import fitz

from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.paper_chunks import PaperChunkRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.repositories.tasks import TaskRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_upload_pdf_creates_task_and_searchable_evidence(client) -> None:
    response = client.post(
        "/api/papers/upload",
        files={
            "file": (
                "paper.pdf",
                _pdf_bytes("Vehicle routing with machine learning evidence"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "pending"
    task = client.get(f"/api/tasks/{payload['task']['id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "completed"

    search = client.get(
        f"/api/papers/{payload['paper_id']}/evidence",
        params={"q": "machine learning"},
    )

    assert search.status_code == 200
    assert search.json()["results"][0]["page_number"] == 1


def test_upload_pdf_uses_ocr_fallback_for_missing_text(client) -> None:
    document = fitz.open()
    document.new_page()
    data = document.tobytes()
    document.close()

    response = client.post(
        "/api/papers/upload",
        files={
            "file": (
                "scanned.pdf",
                data,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    paper_id = response.json()["paper_id"]

    search = client.get(
        f"/api/papers/{paper_id}/evidence",
        params={"q": "OCR"},
    )

    assert search.status_code == 200
    result = search.json()["results"][0]
    assert result["page_number"] == 1
    assert result["is_ocr"] is True
    assert "OCR evidence" in result["text"]


def test_upload_rejects_non_pdf(client) -> None:
    response = client.post(
        "/api/papers/upload",
        files={"file": ("note.txt", b"not pdf", "text/plain")},
    )

    assert response.status_code == 400


def test_upload_rejects_large_pdf(client) -> None:
    response = client.post(
        "/api/papers/upload",
        files={
            "file": (
                "large.pdf",
                b"%PDF-" + (b"x" * (10 * 1024 * 1024 + 1)),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413


def test_quick_analysis_exports_markdown_from_uploaded_chunks(client) -> None:
    upload = client.post(
        "/api/papers/upload",
        files={
            "file": (
                "paper.pdf",
                _pdf_bytes("Vehicle routing with machine learning evidence"),
                "application/pdf",
            )
        },
    )
    paper_id = upload.json()["paper_id"]

    analysis = client.post(f"/api/papers/{paper_id}/quick-analysis")

    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["evidence_pages"] == [1]

    markdown = client.get(f"/api/artifacts/{payload['artifact_id']}/markdown")

    assert markdown.status_code == 200
    assert "How is ML used in routing?" in markdown.text
    assert "Page 1" in markdown.text


def test_compare_papers_creates_comparison_artifact(client) -> None:
    database = client.app.state.database
    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        papers = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id=f"2401.1000{index}",
                        title=f"Routing API Paper {index}",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url=f"https://arxiv.org/abs/2401.1000{index}",
                        pdf_url=f"https://arxiv.org/pdf/2401.1000{index}",
                    ),
                    reason="",
                    purpose_labels=[],
                )
                for index in (1, 2)
            ],
        )
        for index, paper in enumerate(papers, start=1):
            PaperChunkRepository(db).replace_chunks(
                paper.id,
                [
                    {
                        "page_number": 1,
                        "chunk_index": 1,
                        "section": "Introduction",
                        "text": f"Vehicle routing evidence {index}.",
                        "is_ocr": False,
                    },
                    {
                        "page_number": 2,
                        "chunk_index": 2,
                        "section": "Method",
                        "text": f"Method evidence {index}.",
                        "is_ocr": False,
                    },
                ],
            )
        db.commit()

    response = client.post(
        "/api/papers/compare",
        json={"paper_ids": [paper.id for paper in papers]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_pages"][papers[0].id] == [1, 2]

    markdown = client.get(f"/api/artifacts/{payload['artifact_id']}/markdown")

    assert markdown.status_code == 200
    assert "They use different routing methods" in markdown.text


def test_import_arxiv_pdf_creates_completed_task(client) -> None:
    database = client.app.state.database
    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        paper = PaperRepository(db).upsert_arxiv_papers(
            project.id,
            [
                RecommendedPaper(
                    paper=ArxivPaper(
                        arxiv_id="2401.50001",
                        title="Imported API Paper",
                        authors=["A"],
                        abstract="Abstract",
                        published="2024-01-01",
                        categories=["cs.AI"],
                        entry_url="https://arxiv.org/abs/2401.50001",
                        pdf_url="https://arxiv.org/pdf/2401.50001",
                    ),
                    reason="",
                    purpose_labels=[],
                )
            ],
        )[0]
        db.commit()

    response = client.post(f"/api/papers/{paper.id}/import-pdf")

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "pending"
    task = client.get(f"/api/tasks/{response.json()['task']['id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "completed"
    search = client.get(
        f"/api/papers/{paper.id}/evidence",
        params={"q": "downloaded"},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["page_number"] == 1


def test_task_cancel_and_retry_endpoints(client) -> None:
    database = client.app.state.database
    with database.session_factory() as db:
        task = TaskRepository(db).create_task("parse_pdf")
        db.commit()

    cancelled = client.post(f"/api/tasks/{task.id}/cancel")
    retried = client.post(f"/api/tasks/{task.id}/retry")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending"
