from pydantic import BaseModel


class RuntimeSettingsResponse(BaseModel):
    model_configured: bool
    qwen_model: str
    qwen_base_url: str
    ocr_configured: bool
    ocr_language: str
    pdf_max_bytes: int
    pdf_max_pages: int


class DiagnosticResponse(BaseModel):
    configured: bool = True
    available: bool
    message: str
