from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from . import models  # noqa: F401
from .base import Base


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", self._configure_sqlite)
        self.session_factory = sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    @staticmethod
    def _configure_sqlite(dbapi_connection, _) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=MEMORY")
        cursor.close()

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._apply_lightweight_migrations()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts "
                    "USING fts5(chunk_id UNINDEXED, paper_id UNINDEXED, text)"
                )
            )

    def _apply_lightweight_migrations(self) -> None:
        inspector = inspect(self.engine)
        session_columns: set[str] = set()
        message_columns: set[str] = set()
        paper_columns: set[str] = set()
        if inspector.has_table("sessions"):
            session_columns = {
                col["name"] for col in inspector.get_columns("sessions")
            }
        if inspector.has_table("papers"):
            paper_columns = {
                col["name"] for col in inspector.get_columns("papers")
            }
        if inspector.has_table("messages"):
            message_columns = {
                col["name"] for col in inspector.get_columns("messages")
            }
        with self.engine.begin() as connection:
            if "title" not in session_columns:
                connection.execute(
                    text(
                        "ALTER TABLE sessions "
                        "ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"
                    )
                )
            if "updated_at" not in session_columns:
                connection.execute(
                    text(
                        "ALTER TABLE sessions "
                        "ADD COLUMN updated_at DATETIME"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE sessions SET updated_at = created_at "
                        "WHERE updated_at IS NULL"
                    )
                )
            if "favorited" not in paper_columns:
                connection.execute(
                    text(
                        "ALTER TABLE papers "
                        "ADD COLUMN favorited BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            if "metadata_json" not in message_columns:
                connection.execute(
                    text(
                        "ALTER TABLE messages "
                        "ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                    )
                )

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
