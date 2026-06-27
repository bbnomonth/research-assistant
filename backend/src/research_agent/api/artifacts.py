import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact, ConversationSession, Message, Paper
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.schemas.artifacts import (
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactSourceLink,
    ArtifactSummary,
    ArtifactUpdateRequest,
    extract_source_links,
)


router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=ArtifactListResponse,
)
def list_project_artifacts(project_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        artifacts = ArtifactRepository(db).list_for_project(project_id)
        return {
            "artifacts": [
                ArtifactSummary.from_model(
                    artifact,
                    source_links=_resolve_source_links(db, artifact),
                )
                for artifact in artifacts
            ]
        }


def _resolve_source_links(
    db: Session,
    artifact: Artifact,
) -> List[ArtifactSourceLink]:
    content = _load_content(artifact)
    links = extract_source_links(
        artifact_type=artifact.artifact_type,
        project_id=artifact.project_id,
        content=content,
    )

    if not _has_link(links, "session"):
        session_id = _infer_source_session_id(db, artifact)
        if session_id:
            links.append(
                ArtifactSourceLink(
                    source_type="session",
                    target_id=session_id,
                    project_id=artifact.project_id,
                    label="来源对话",
                )
            )

    if not _has_link(links, "paper"):
        paper_id = _infer_source_paper_id(db, artifact, content)
        if paper_id:
            links.append(
                ArtifactSourceLink(
                    source_type="paper",
                    target_id=paper_id,
                    project_id=artifact.project_id,
                    label="来源论文",
                )
            )

    return _dedupe_links(links)


def _load_content(artifact: Artifact) -> Dict[str, Any]:
    try:
        content = json.loads(artifact.content_json or "{}")
    except json.JSONDecodeError:
        return {}
    return content if isinstance(content, dict) else {}


def _has_link(links: List[ArtifactSourceLink], source_type: str) -> bool:
    return any(link.source_type == source_type for link in links)


def _dedupe_links(links: List[ArtifactSourceLink]) -> List[ArtifactSourceLink]:
    deduped: List[ArtifactSourceLink] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        key = (link.source_type, link.target_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def _infer_source_session_id(db: Session, artifact: Artifact) -> Optional[str]:
    mode_by_artifact_type = {
        "framework_card": "framework_building",
        "topic_guidance_plan": "topic_guidance",
        "guided_reading_note": "paper_reading",
        "literature_card": "literature_discovery",
    }
    mode = mode_by_artifact_type.get(artifact.artifact_type)
    if mode is None:
        return None

    rows = db.execute(
        select(Message.session_id, Message.created_at)
        .join(ConversationSession, Message.session_id == ConversationSession.id)
        .where(
            ConversationSession.project_id == artifact.project_id,
            Message.role == "assistant",
            Message.mode == mode,
        )
    ).all()
    rows = sorted(
        rows,
        key=lambda row: _seconds_apart(row[1], artifact.created_at),
    )
    for session_id, message_created_at in rows:
        if _seconds_apart(message_created_at, artifact.created_at) <= 3600:
            return session_id
    return None


def _seconds_apart(left: datetime, right: datetime) -> float:
    return abs((left - right).total_seconds())


def _infer_source_paper_id(
    db: Session,
    artifact: Artifact,
    content: Dict[str, Any],
) -> Optional[str]:
    explicit_id = content.get("paper_id") or content.get("id")
    if isinstance(explicit_id, str) and explicit_id:
        return explicit_id

    title_candidates = [
        content.get("paper_title"),
        content.get("title"),
        _strip_artifact_title_prefix(artifact.title),
    ]
    for title in title_candidates:
        if not isinstance(title, str) or not title.strip():
            continue
        paper_id = db.scalar(
            select(Paper.id)
            .where(
                Paper.project_id == artifact.project_id,
                Paper.title == title.strip(),
            )
            .limit(1)
        )
        if paper_id:
            return paper_id
    return None


def _strip_artifact_title_prefix(title: str) -> str:
    for separator in ("：", ":"):
        if separator in title:
            return title.split(separator, 1)[1].strip()
    return title.strip()


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(artifact_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        artifact = ArtifactRepository(db).get(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return ArtifactResponse.from_model(artifact)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def update_artifact(
    artifact_id: str,
    payload: ArtifactUpdateRequest,
    request: Request,
):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            artifact = ArtifactRepository(db).update_artifact(
                artifact_id=artifact_id,
                title=payload.title,
                content=payload.content,
                markdown=payload.markdown,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
        return ArtifactResponse.from_model(artifact)


@router.get("/artifacts/{artifact_id}/markdown")
def export_artifact_markdown(artifact_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            markdown = ArtifactRepository(db).to_markdown(artifact_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return PlainTextResponse(markdown)


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: str, request: Request):
    database = request.app.state.database
    with database.session_factory() as db:
        try:
            ArtifactRepository(db).delete_artifact(artifact_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        db.commit()
    return None
