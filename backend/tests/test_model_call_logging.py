import time

from sqlalchemy import select

from research_agent.db.engine import Database
from research_agent.db.models import ModelCallLog
from research_agent.services.model_call_logging import record_model_call


def test_model_call_log_stores_only_redacted_metrics(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        record_model_call(
            db=db,
            task_type="guided_reading",
            model="fake-model",
            started=time.perf_counter(),
            retries=1,
            success=False,
            error=RuntimeError("secret prompt and private paper text"),
        )
        db.commit()
        log = db.scalar(select(ModelCallLog))

    assert log.task_type == "guided_reading"
    assert log.model == "fake-model"
    assert log.retries == 1
    assert log.success == 0
    assert log.error_type == "RuntimeError"
    assert "secret" not in repr(log.__dict__)
