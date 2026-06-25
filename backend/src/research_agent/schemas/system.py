from typing import Optional

from pydantic import BaseModel


class RuntimeSettingsResponse(BaseModel):
    model_configured: bool
    qwen_model: str
    qwen_base_url: str
    ocr_configured: bool
    ocr_language: str
    pdf_max_bytes: int
    pdf_max_pages: int
    privacy: "PrivacySettingsResponse"


class PrivacySettingsResponse(BaseModel):
    pii_scrub: bool
    local_only: bool
    data_ttl_days: int


class DiagnosticResponse(BaseModel):
    configured: bool = True
    available: bool
    message: str


class WipeDataResponse(BaseModel):
    wiped: bool
    removed_uploads: int
    removed_messages: int
    removed_sessions: int
    removed_projects: int
    message: Optional[str] = None
