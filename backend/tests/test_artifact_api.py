import fitz


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _create_artifact(client) -> dict:
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
    return client.post(f"/api/papers/{paper_id}/quick-analysis").json()


def test_artifact_api_reads_lists_updates_and_exports(client) -> None:
    created = _create_artifact(client)
    artifact_id = created["artifact_id"]

    detail = client.get(f"/api/artifacts/{artifact_id}")

    assert detail.status_code == 200
    artifact = detail.json()
    assert artifact["id"] == artifact_id
    assert artifact["artifact_type"] == "literature_card"

    listing = client.get(f"/api/projects/{artifact['project_id']}/artifacts")

    assert listing.status_code == 200
    assert listing.json()["artifacts"][0]["id"] == artifact_id

    updated = client.patch(
        f"/api/artifacts/{artifact_id}",
        json={
            "title": "Edited card",
            "markdown": "# Edited card",
            "content": {"research_question": "Edited question"},
        },
    )

    assert updated.status_code == 200
    assert updated.json()["title"] == "Edited card"
    assert updated.json()["content"]["research_question"] == "Edited question"

    markdown = client.get(f"/api/artifacts/{artifact_id}/markdown")

    assert markdown.status_code == 200
    assert markdown.text == "# Edited card"
