import fitz


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
    assert payload["task"]["status"] == "completed"
    task = client.get(f"/api/tasks/{payload['task']['id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "completed"

    search = client.get(
        f"/api/papers/{payload['paper_id']}/evidence",
        params={"q": "machine learning"},
    )

    assert search.status_code == 200
    assert search.json()["results"][0]["page_number"] == 1


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
