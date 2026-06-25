from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from research_agent.config import Settings
from research_agent.db.models import ConversationSession, Message, utc_now
from research_agent.main import create_app
from research_agent.repositories.conversations import ConversationRepository
from research_agent.schemas.literature import ArxivPaper
from research_agent.services.privacy import scrub_pii


def test_scrub_pii_replaces_emails_phones_and_ids():
    text = (
        "Please contact alice@example.com or +8613812345678. "
        "Backup: bob@school.edu, 13800001234. ID 110101199003078812 and SSN 123-45-6789."
    )
    cleaned = scrub_pii(text)
    assert "[email]" in cleaned
    assert "[phone]" in cleaned
    assert "[id]" in cleaned
    assert "[ssn]" in cleaned
    assert "alice@example.com" not in cleaned
    assert "13812345678" not in cleaned
    assert "110101199003078812" not in cleaned


def test_scrub_pii_is_noop_when_text_has_no_pii():
    assert scrub_pii("The model performed well on the benchmark.") == (
        "The model performed well on the benchmark."
    )


def test_wipe_data_endpoint_removes_messages_projects_and_papers(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    sample = upload_dir / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4\n%fake")

    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "wipe-test.sqlite3"))
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))

    app = create_app()
    app.state.database.create_schema()

    with TestClient(app) as client:
        # Seed a project/session/message via the repository directly so the
        # wipe endpoint has something to remove.
        with app.state.database.session_factory() as db:
            repo = ConversationRepository(db)
            project, session = repo.ensure_conversation(
                project_id=None, session_id=None
            )
            repo.add_message(
                session_id=session.id,
                role="user",
                content="hello",
                mode=None,
            )
            db.commit()

        response = client.post("/api/system/wipe-data")
        assert response.status_code == 200
        body = response.json()
        assert body["wiped"] is True
        assert body["removed_projects"] >= 1
        assert body["removed_messages"] >= 1
        assert body["removed_uploads"] >= 1

        # The sample file is gone.
        assert not sample.exists()

        # Project list is empty afterwards.
        listing = client.get("/api/projects").json()
        assert listing["projects"] == []


def test_settings_exposes_privacy_block():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/system/settings")
        assert response.status_code == 200
        body = response.json()
        assert "privacy" in body
        assert set(body["privacy"].keys()) == {
            "pii_scrub",
            "local_only",
            "data_ttl_days",
        }


class LocalOnlyArxivProvider:
    async def search(self, query):
        assert "车辆路径" in query
        return [
            ArxivPaper(
                arxiv_id="2401.90001",
                title="Local-only routing paper",
                authors=["A"],
                abstract="Routing abstract",
                published="2024-01-01",
                categories=["cs.AI"],
                entry_url="https://arxiv.org/abs/2401.90001",
                pdf_url="https://arxiv.org/pdf/2401.90001",
            )
        ]


def test_local_only_mode_keeps_literature_discovery_available(tmp_path):
    settings = Settings(
        app_root=tmp_path,
        database_path=tmp_path / "local.sqlite3",
        upload_dir=tmp_path / "uploads",
        privacy_local_only=True,
    )
    app = create_app(
        settings=settings,
        arxiv_provider=LocalOnlyArxivProvider(),
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"content": "搜索车辆路径优化文献"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "literature_discovery"' in body
    assert "event: search_results" in body
    assert "2401.90001" in body
    assert "event: done" in body


def test_startup_ttl_removes_only_expired_conversations(tmp_path):
    settings = Settings(
        app_root=tmp_path,
        database_path=tmp_path / "ttl.sqlite3",
        upload_dir=tmp_path / "uploads",
        privacy_data_ttl_days=7,
    )
    seed_app = create_app(settings=settings)
    seed_app.state.database.create_schema()
    with seed_app.state.database.session_factory() as db:
        repository = ConversationRepository(db)
        old_project, old_session = repository.ensure_conversation(None, None)
        old_session.created_at = utc_now() - timedelta(days=10)
        repository.add_message(old_session.id, "user", "expired")

        new_project, new_session = repository.ensure_conversation(None, None)
        repository.add_message(new_session.id, "user", "recent")
        db.commit()

    app = create_app(settings=settings)
    with TestClient(app):
        pass

    with app.state.database.session_factory() as db:
        sessions = list(db.scalars(select(ConversationSession)))
        messages = list(db.scalars(select(Message)))

    assert [session.id for session in sessions] == [new_session.id]
    assert [message.content for message in messages] == ["recent"]
    assert old_project.id != new_project.id
