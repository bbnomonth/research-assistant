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
    pdf_max_bytes: int = 10 * 1024 * 1024
    pdf_max_pages: int = 60

    @property
    def resolved_database_path(self) -> Path:
        return self._resolve(self.database_path)

    @property
    def resolved_upload_dir(self) -> Path:
        return self._resolve(self.upload_dir)

    @property
    def model_configured(self) -> bool:
        candidate = (self.qwen_api_key or "").strip()
        return candidate not in PLACEHOLDER_API_KEYS

    def _resolve(self, value: Path) -> Path:
        return value if value.is_absolute() else self.app_root / value

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Settings":
        if env_file is None:
            env_file = Path.cwd() / "backend" / ".env"
        load_dotenv(dotenv_path=env_file, override=False)
        return cls(
            app_root=Path(os.getenv("APP_ROOT", Path.cwd())),
            database_path=Path(os.getenv("DATABASE_PATH", "data/app.sqlite3")),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "data/uploads")),
            qwen_api_key=os.getenv("DASHSCOPE_API_KEY"),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            qwen_model=os.getenv("QWEN_MODEL", "qwen3.7-plus"),
        )
