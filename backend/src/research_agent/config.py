from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


PLACEHOLDER_API_KEYS = {
    "",
    "replace-with-your-api-key",
    "your-api-key-here",
}


@dataclass(frozen=True)
class Settings:
    app_root: Path = Path(__file__).resolve().parents[3]
    database_path: Path = Path("data/app.sqlite3")
    upload_dir: Path = Path("data/uploads")
    qwen_api_key: Optional[str] = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.7-plus"
    tesseract_executable: Optional[str] = None
    ocr_language: str = "chi_sim+eng"
    pdf_max_bytes: int = 10 * 1024 * 1024
    pdf_max_pages: int = 60
    cors_allowed_origins: tuple[str, ...] = ()
    privacy_pii_scrub: bool = False
    privacy_local_only: bool = False
    privacy_data_ttl_days: int = 0

    @property
    def resolved_database_path(self) -> Path:
        return self._resolve(self.database_path)

    @property
    def resolved_upload_dir(self) -> Path:
        return self._resolve(self.upload_dir)

    @property
    def model_configured(self) -> bool:
        candidate = (self.qwen_api_key or "").strip()
        return candidate not in PLACEHOLDER_API_KEYS and not self.privacy_local_only

    def _resolve(self, value: Path) -> Path:
        return value if value.is_absolute() else self.app_root / value

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Settings":
        default_app_root = Path(__file__).resolve().parents[3]
        if env_file is None:
            candidates = (
                default_app_root / "backend" / ".env",
                Path.cwd() / "backend" / ".env",
                Path.cwd() / ".env",
            )
            env_file = next((path for path in candidates if path.exists()), candidates[0])
        load_dotenv(dotenv_path=env_file, override=False)
        return cls(
            app_root=Path(os.getenv("APP_ROOT", default_app_root)),
            database_path=Path(os.getenv("DATABASE_PATH", "data/app.sqlite3")),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "data/uploads")),
            qwen_api_key=os.getenv("DASHSCOPE_API_KEY"),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            qwen_model=os.getenv("QWEN_MODEL", "qwen3.7-plus"),
            tesseract_executable=os.getenv("TESSERACT_EXECUTABLE"),
            ocr_language=os.getenv("OCR_LANGUAGE", "chi_sim+eng"),
            cors_allowed_origins=_csv_env("CORS_ALLOWED_ORIGINS"),
            privacy_pii_scrub=_bool_env("PRIVACY_PII_SCRUB", False),
            privacy_local_only=_bool_env("PRIVACY_LOCAL_ONLY", False),
            privacy_data_ttl_days=int(os.getenv("PRIVACY_DATA_TTL_DAYS", "0") or 0),
        )


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip().rstrip("/") for item in raw.split(",") if item.strip())
