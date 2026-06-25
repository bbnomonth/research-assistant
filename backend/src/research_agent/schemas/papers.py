from typing import List, Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    status: str
    progress: int
    paper_id: Optional[str] = None
    error_message: Optional[str] = None


class UploadResponse(BaseModel):
    paper_id: str
    task: TaskResponse


class EvidenceItem(BaseModel):
    chunk_id: str
    page_number: int
    section: str
    text: str
    is_ocr: bool


class EvidenceSearchResponse(BaseModel):
    results: List[EvidenceItem]


class QuickAnalysisResponse(BaseModel):
    artifact_id: str
    title: str
    evidence_pages: List[int]


class PaperComparisonRequest(BaseModel):
    paper_ids: List[str]


class PaperComparisonResponse(BaseModel):
    artifact_id: str
    title: str
    evidence_pages: dict[str, List[int]]


class FavoritePaperRequest(BaseModel):
    project_id: str
    arxiv_id: str
    favorited: bool
