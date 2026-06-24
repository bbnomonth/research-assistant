from sqlalchemy import inspect

from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository


def test_database_creates_foundation_tables(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    names = set(inspect(database.engine).get_table_names())

    assert {"projects", "sessions", "messages", "model_call_logs"} <= names


def test_repository_auto_creates_project_session_and_messages(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        repo = ConversationRepository(db)
        project, session = repo.ensure_conversation(None, None)
        user_message = repo.add_message(session.id, "user", "解释强化学习")
        assistant_message = repo.add_message(
            session.id,
            "assistant",
            "强化学习通过奖励信号学习策略。",
            mode="general_qa",
        )
        db.commit()

        assert project.name == "未命名项目"
        assert user_message.session_id == session.id
        assert assistant_message.mode == "general_qa"
        assert [m.role for m in repo.list_recent_messages(session.id, 20)] == [
            "user",
            "assistant",
        ]


def test_repository_rejects_session_from_another_project(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        repo = ConversationRepository(db)
        project_a, session_a = repo.ensure_conversation(None, None)
        project_b, _ = repo.ensure_conversation(None, None)

        try:
            repo.ensure_conversation(project_b.id, session_a.id)
        except LookupError as exc:
            assert str(exc) == "session not found for project"
        else:
            raise AssertionError("expected LookupError")
