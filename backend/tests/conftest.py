import pytest
from fastapi.testclient import TestClient

from research_agent.config import Settings
from research_agent.main import create_app
from research_agent.services.model_gateway import FakeModelGateway


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        app_root=tmp_path,
        database_path=tmp_path / "test.sqlite3",
        upload_dir=tmp_path / "uploads",
        qwen_api_key=None,
    )
    app = create_app(
        settings=settings,
        model_gateway=FakeModelGateway(["测试", "回答"]),
    )
    with TestClient(app) as test_client:
        yield test_client

