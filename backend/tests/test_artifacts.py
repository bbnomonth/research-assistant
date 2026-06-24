from research_agent.db.engine import Database
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.conversations import ConversationRepository


def test_artifact_repository_saves_and_exports_markdown(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        repository = ArtifactRepository(db)
        artifact = repository.create_artifact(
            project_id=project.id,
            artifact_type="literature_card",
            title="Paper card",
            content={"research_question": "How does X affect Y?"},
            markdown="# Paper card\n\nHow does X affect Y?",
        )
        db.commit()

        loaded = repository.get(artifact.id)

    assert loaded is not None
    assert loaded.title == "Paper card"
    assert repository.to_markdown(artifact.id).startswith("# Paper card")


def test_artifact_repository_lists_and_updates_project_artifacts(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        project, _ = ConversationRepository(db).ensure_conversation(None, None)
        repository = ArtifactRepository(db)
        artifact = repository.create_artifact(
            project_id=project.id,
            artifact_type="diagnosis",
            title="Draft",
            content={"status": "draft"},
            markdown="# Draft",
        )
        updated = repository.update_artifact(
            artifact.id,
            title="Edited",
            content={"status": "edited"},
            markdown="# Edited",
        )
        db.commit()

        artifacts = repository.list_for_project(project.id)

    assert [item.id for item in artifacts] == [artifact.id]
    assert updated.title == "Edited"
    assert repository.to_markdown(artifact.id) == "# Edited"
