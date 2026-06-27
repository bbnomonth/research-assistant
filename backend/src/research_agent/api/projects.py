from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from research_agent.db.models import (
    Artifact,
    ConversationSession,
    Message,
    Paper,
    PaperChunk,
    Project,
    Task,
)
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.projects import (
    MessageListResponse,
    MessageResponse,
    PaperListResponse,
    PaperSummary,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    SessionListResponse,
    SessionResponse,
    SessionUpdateRequest,
)


router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        projects = ConversationRepository(db).list_projects()
        return {
            "projects": [
                ProjectResponse.from_model(project) for project in projects
            ]
        }


@router.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        project = ConversationRepository(db).create_project(
            name=payload.name,
            profile=payload.profile,
        )
        db.commit()
        return ProjectResponse.from_model(project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        project = ConversationRepository(db).get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return ProjectResponse.from_model(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    request: Request,
):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            project = ConversationRepository(db).update_project(
                project_id,
                name=payload.name,
                profile=payload.profile,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
        return ProjectResponse.from_model(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        project = repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")

        session_ids = [
            row[0]
            for row in db.query(ConversationSession.id)
            .filter(ConversationSession.project_id == project_id)
            .all()
        ]
        if session_ids:
            db.query(Message).filter(Message.session_id.in_(session_ids)).delete(
                synchronize_session=False,
            )

        paper_ids = [
            row[0]
            for row in db.query(Paper.id).filter(Paper.project_id == project_id).all()
        ]
        for paper_id in paper_ids:
            db.execute(
                text("DELETE FROM paper_chunks_fts WHERE paper_id = :paper_id"),
                {"paper_id": paper_id},
            )
        if paper_ids:
            db.query(Task).filter(Task.paper_id.in_(paper_ids)).delete(
                synchronize_session=False,
            )
            db.query(PaperChunk).filter(PaperChunk.paper_id.in_(paper_ids)).delete(
                synchronize_session=False,
            )
            db.query(Paper).filter(Paper.id.in_(paper_ids)).delete(
                synchronize_session=False,
            )

        db.query(Artifact).filter(Artifact.project_id == project_id).delete(
            synchronize_session=False,
        )
        db.query(ConversationSession).filter(
            ConversationSession.project_id == project_id,
        ).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project_id).delete(
            synchronize_session=False,
        )
        db.commit()
    return None


@router.get(
    "/projects/{project_id}/sessions",
    response_model=SessionListResponse,
)
def list_project_sessions(project_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        if repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="project not found")
        sessions = repository.list_sessions(project_id)
        return {
            "sessions": [
                SessionResponse.from_model(session) for session in sessions
            ]
        }


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageListResponse,
)
def list_session_messages(session_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        if repository.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        messages = repository.list_messages(session_id)
        return {
            "messages": [
                MessageResponse.from_model(message) for message in messages
            ]
        }


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionResponse,
)
def update_session(
    session_id: str,
    payload: SessionUpdateRequest,
    request: Request,
):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            session = ConversationRepository(db).rename_session(
                session_id,
                payload.title or "",
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
        return SessionResponse.from_model(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
)
def delete_session(session_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        if repository.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        repository.db.query(Message).filter(
            Message.session_id == session_id
        ).delete(synchronize_session=False)
        repository.db.delete(repository.get_session(session_id))
        db.commit()
    return None


@router.get(
    "/projects/{project_id}/papers",
    response_model=PaperListResponse,
)
def list_project_papers(
    project_id: str,
    request: Request,
    limit: int = 50,
):
    safe_limit = max(1, min(limit, 200))
    database = request.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        if repository.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="project not found")
        papers = PaperRepository(db).list_for_project(project_id, limit=safe_limit)
        return {
            "papers": [PaperSummary.from_model(paper) for paper in papers]
        }
