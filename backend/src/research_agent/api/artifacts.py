from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.schemas.artifacts import (
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactSummary,
    ArtifactUpdateRequest,
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
                ArtifactSummary.from_model(artifact)
                for artifact in artifacts
            ]
        }


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
