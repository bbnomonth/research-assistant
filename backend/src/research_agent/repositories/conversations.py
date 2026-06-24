from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_agent.db.models import ConversationSession, Message, Project


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_conversation(
        self,
        project_id: Optional[str],
        session_id: Optional[str],
    ) -> Tuple[Project, ConversationSession]:
        if project_id is None:
            project = Project()
            self.db.add(project)
            self.db.flush()
        else:
            project = self.db.get(Project, project_id)
            if project is None:
                raise LookupError("project not found")

        if session_id is None:
            conversation = ConversationSession(project_id=project.id)
            self.db.add(conversation)
            self.db.flush()
        else:
            conversation = self.db.get(ConversationSession, session_id)
            if conversation is None or conversation.project_id != project.id:
                raise LookupError("session not found for project")

        return project, conversation

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        mode: Optional[str] = None,
    ) -> Message:
        current_max = self.db.scalar(
            select(func.max(Message.sequence)).where(
                Message.session_id == session_id
            )
        )
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            mode=mode,
            sequence=(current_max or 0) + 1,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def list_recent_messages(
        self,
        session_id: str,
        limit: int,
    ) -> List[Message]:
        statement = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.sequence.desc())
            .limit(limit)
        )
        messages = list(self.db.scalars(statement))
        messages.reverse()
        return messages
