from typing import List, Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    status: str
    progress: int
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
