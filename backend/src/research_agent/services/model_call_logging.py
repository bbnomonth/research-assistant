import time
from typing import Optional

from sqlalchemy.orm import Session

from research_agent.db.models import ModelCallLog


def record_model_call(
    db: Optional[Session],
    task_type: str,
    model: str,
    started: float,
    retries: int,
    success: bool,
    error: Optional[BaseException] = None,
) -> None:
    if db is None:
        return
    db.add(
        ModelCallLog(
            task_type=task_type,
            model=model,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            retries=retries,
            success=1 if success else 0,
            error_type=type(error).__name__ if error is not None else None,
        )
    )
    db.flush()
