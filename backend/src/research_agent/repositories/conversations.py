import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_agent.db.models import ConversationSession, Message, Project


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    def list_projects(self) -> List[Project]:
        return list(
            self.db.scalars(
                select(Project).order_by(Project.updated_at.desc())
            )
        )

    def get_project(self, project_id: str) -> Optional[Project]:
        return self.db.get(Project, project_id)

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Project:
        project = self.get_project(project_id)
        if project is None:
            raise LookupError("project not found")
        if name is not None:
            project.name = name.strip()
        if profile is not None:
            project.profile_json = json.dumps(profile, ensure_ascii=False)
        self.db.flush()
        return project

    def get_session(
        self,
        session_id: str,
    ) -> Optional[ConversationSession]:
        return self.db.get(ConversationSession, session_id)

    def list_sessions(self, project_id: str) -> List[ConversationSession]:
        return list(
            self.db.scalars(
                select(ConversationSession)
                .where(ConversationSession.project_id == project_id)
                .order_by(ConversationSession.updated_at.desc())
            )
        )

    def get_session_with_messages(
        self,
        session_id: str,
    ) -> Optional[Tuple[ConversationSession, List[Message]]]:
        session = self.db.get(ConversationSession, session_id)
        if session is None:
            return None
        messages = list(
            self.db.scalars(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.sequence)
            )
        )
        return session, messages

    def auto_title_session(
        self,
        session_id: str,
        title: str,
    ) -> ConversationSession:
        session = self.db.get(ConversationSession, session_id)
        if session is None:
            raise LookupError("session not found")
        session.title = title.strip()[:200]
        session.updated_at = utc_now()
        self.db.flush()
        return session

    def rename_session(
        self,
        session_id: str,
        title: str,
    ) -> ConversationSession:
        session = self.db.get(ConversationSession, session_id)
        if session is None:
            raise LookupError("session not found")
        session.title = title.strip()[:200]
        session.updated_at = utc_now()
        self.db.flush()
        return session

    def touch_session(self, session_id: str) -> None:
        session = self.db.get(ConversationSession, session_id)
        if session is not None:
            session.updated_at = utc_now()

    def list_messages(self, session_id: str) -> List[Message]:
        return list(
            self.db.scalars(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.sequence)
            )
        )
