from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_agent.db.models import Task


class TaskRepository:
    ACTIVE_STATUSES = {"pending", "processing"}
    RETRYABLE_STATUSES = {"failed", "cancelled", "interrupted"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(
        self,
        task_type: str,
        paper_id: Optional[str] = None,
    ) -> Task:
        task = Task(task_type=task_type, paper_id=paper_id)
        self.db.add(task)
        self.db.flush()
        return task

    def cancel(self, task_id: str) -> Task:
        task = self._require(task_id)
        if task.status not in self.ACTIVE_STATUSES:
            raise ValueError(f"cannot cancel task in {task.status} status")
        task.status = "cancelled"
        task.error_message = None
        self.db.flush()
        return task

    def retry(self, task_id: str) -> Task:
        task = self._require(task_id)
        if task.status not in self.RETRYABLE_STATUSES:
            raise ValueError(f"cannot retry task in {task.status} status")
        task.status = "pending"
        task.progress = 0
        task.error_message = None
        self.db.flush()
        return task

    def mark_active_interrupted(self) -> int:
        tasks = list(
            self.db.scalars(
                select(Task).where(Task.status.in_(self.ACTIVE_STATUSES))
            )
        )
        for task in tasks:
            task.status = "interrupted"
            task.error_message = "task interrupted by application restart"
        self.db.flush()
        return len(tasks)

    def _require(self, task_id: str) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise LookupError("task not found")
        return task

    def update_status(
        self,
        task_id: str,
        status: str,
        progress: int,
        error_message: Optional[str] = None,
    ) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise LookupError("task not found")
        task.status = status
        task.progress = progress
        task.error_message = error_message
        self.db.flush()
        return task
