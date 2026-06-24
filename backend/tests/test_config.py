from pathlib import Path

from research_agent.config import Settings


def test_settings_resolve_data_paths_from_app_root(tmp_path: Path) -> None:
    settings = Settings(
        app_root=tmp_path,
        database_path=Path("data/app.sqlite3"),
        upload_dir=Path("data/uploads"),
        qwen_api_key=None,
    )

    assert settings.resolved_database_path == tmp_path / "data/app.sqlite3"
    assert settings.resolved_upload_dir == tmp_path / "data/uploads"
    assert settings.qwen_model == "qwen3.7-plus"
    assert settings.pdf_max_bytes == 10 * 1024 * 1024
    assert settings.pdf_max_pages == 60


def test_settings_load_qwen_placeholders_from_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "replace-with-your-api-key")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")

    settings = Settings.from_env()

    assert settings.qwen_api_key == "replace-with-your-api-key"
    assert settings.qwen_model == "qwen3.7-plus"
