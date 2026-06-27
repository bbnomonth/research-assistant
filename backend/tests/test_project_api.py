from sqlalchemy import text

from research_agent.db.models import Artifact, Paper, PaperChunk, Task
from research_agent.repositories.conversations import ConversationRepository


def _seed_project(client):
    database = client.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        project, session = repository.ensure_conversation(None, None)
        project.name = "Original project"
        repository.add_message(session.id, "user", "First question")
        repository.add_message(session.id, "assistant", "First answer")
        db.commit()
        return project.id, session.id


def test_project_api_lists_reads_and_renames_project(client) -> None:
    project_id, _ = _seed_project(client)

    listing = client.get("/api/projects")
    detail = client.get(f"/api/projects/{project_id}")
    updated = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Routing research"},
    )

    assert listing.status_code == 200
    assert listing.json()["projects"][0]["id"] == project_id
    assert detail.status_code == 200
    assert detail.json()["name"] == "Original project"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Routing research"


def test_project_api_returns_sessions_and_ordered_messages(client) -> None:
    project_id, session_id = _seed_project(client)

    sessions = client.get(f"/api/projects/{project_id}/sessions")
    messages = client.get(f"/api/sessions/{session_id}/messages")

    assert sessions.status_code == 200
    assert sessions.json()["sessions"][0]["id"] == session_id
    assert messages.status_code == 200
    assert [item["content"] for item in messages.json()["messages"]] == [
        "First question",
        "First answer",
    ]


def test_project_api_deletes_session_and_messages(client) -> None:
    project_id, session_id = _seed_project(client)

    deleted = client.delete(f"/api/sessions/{session_id}")
    sessions = client.get(f"/api/projects/{project_id}/sessions")
    messages = client.get(f"/api/sessions/{session_id}/messages")

    assert deleted.status_code == 204
    assert sessions.status_code == 200
    assert sessions.json()["sessions"] == []
    assert messages.status_code == 404


def test_project_api_deletes_project_and_related_records(client) -> None:
    project_id, session_id = _seed_project(client)
    database = client.app.state.database
    with database.session_factory() as db:
        paper = Paper(
            project_id=project_id,
            arxiv_id="2501.00001",
            title="Routing paper",
            authors_json="[]",
            abstract="abstract",
            published="2025-01-01",
            categories_json="[]",
            entry_url="https://example.com/abs/2501.00001",
            pdf_url="https://example.com/pdf/2501.00001",
        )
        db.add(paper)
        db.flush()
        chunk = PaperChunk(
            paper_id=paper.id,
            page_number=1,
            chunk_index=1,
            section="Intro",
            text="heuristic routing",
        )
        db.add(chunk)
        db.flush()
        db.execute(
            text(
                "INSERT INTO paper_chunks_fts(chunk_id, paper_id, text) "
                "VALUES (:chunk_id, :paper_id, :text)"
            ),
            {
                "chunk_id": chunk.id,
                "paper_id": paper.id,
                "text": chunk.text,
            },
        )
        db.add(Task(task_type="parse_pdf", paper_id=paper.id))
        db.add(
            Artifact(
                project_id=project_id,
                artifact_type="framework_card",
                title="Framework",
            )
        )
        db.commit()
        paper_id = paper.id

    deleted = client.delete(f"/api/projects/{project_id}")

    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/messages").status_code == 404
    with database.session_factory() as db:
        assert db.query(Paper).filter(Paper.project_id == project_id).count() == 0
        assert db.query(PaperChunk).filter(PaperChunk.paper_id == paper_id).count() == 0
        assert db.query(Task).filter(Task.paper_id == paper_id).count() == 0
        assert db.query(Artifact).filter(Artifact.project_id == project_id).count() == 0
        fts_rows = db.execute(
            text("SELECT count(*) FROM paper_chunks_fts WHERE paper_id = :paper_id"),
            {"paper_id": paper_id},
        ).scalar_one()
        assert fts_rows == 0


def test_project_api_updates_structured_profile(client) -> None:
    project_id, _ = _seed_project(client)

    response = client.patch(
        f"/api/projects/{project_id}",
        json={"profile": {"topic": "vehicle routing", "method": "experiment"}},
    )

    assert response.status_code == 200
    assert response.json()["profile"] == {
        "topic": "vehicle routing",
        "method": "experiment",
    }


def test_project_api_returns_404_for_unknown_ids(client) -> None:
    assert client.get("/api/projects/missing").status_code == 404
    assert client.get("/api/sessions/missing/messages").status_code == 404
