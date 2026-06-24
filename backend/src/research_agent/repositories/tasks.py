from typing import Optional

from sqlalchemy.orm import Session

from research_agent.db.models import Task


class TaskRepository:
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

