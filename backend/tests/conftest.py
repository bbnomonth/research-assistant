import pytest
from fastapi.testclient import TestClient

from research_agent.config import Settings
from research_agent.main import create_app
from research_agent.schemas.literature import ArxivPaper


class ApiFakeGateway:
    model_name = "fake-model"

    async def stream_chat(self, messages):
        prompt = messages[-1]["content"]
        if "英文 arXiv 检索式" in prompt:
            yield '{"english_query":"vehicle routing"}'
        elif "候选文献" in prompt:
            yield (
                '[{"arxiv_id":"2401.00001","reason":"高度相关",'
                '"purpose_labels":["方法相似"]}]'
            )
        else:
            yield "测试"
            yield "回答"

    async def aclose(self):
        return None


class ApiFakeArxivProvider:
    async def search(self, query):
        assert query == "vehicle routing"
        return [
            ArxivPaper(
                arxiv_id=f"2401.0000{index}",
                title=f"Paper {index}",
                authors=[f"Author {index}"],
                abstract=f"Abstract {index}",
                published="2024-01-01",
                categories=["cs.AI"],
                entry_url=f"https://arxiv.org/abs/2401.0000{index}",
                pdf_url=f"https://arxiv.org/pdf/2401.0000{index}",
            )
            for index in range(1, 6)
        ]


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
        model_gateway=ApiFakeGateway(),
        arxiv_provider=ApiFakeArxivProvider(),
    )
    with TestClient(app) as test_client:
        yield test_client
