from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
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
        self.session_factory = sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts "
                    "USING fts5(chunk_id UNINDEXED, paper_id UNINDEXED, text)"
                )
            )

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
