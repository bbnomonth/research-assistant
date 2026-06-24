from sqlalchemy import inspect

from research_agent.db.engine import Database


def test_database_creates_foundation_tables(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    names = set(inspect(database.engine).get_table_names())

    assert {"projects", "sessions", "messages", "model_call_logs"} <= names
