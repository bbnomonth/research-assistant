import pytest
import fitz
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
        elif "evidence-bound literature card" in prompt:
            yield (
                '{"research_topic":"Vehicle routing",'
                '"research_question":"How is ML used in routing?",'
                '"method":"Review",'
                '"contribution":"Summarizes parsed evidence",'
                '"risks":["Evidence is limited"]}'
            )
        elif "evidence-bound paper comparison" in prompt:
            yield (
                '{"overview":"Both papers study routing.",'
                '"findings":[{"dimension":"Method",'
                '"summary":"They use different routing methods.",'
                '"evidence_notes":["Evidence is page-bound."]}],'
                '"transferable_insights":["Compare method fit before reuse."],'
                '"risks":["Evidence is limited"]}'
            )
        elif "research-design diagnosis" in prompt:
            yield (
                '{"topic_summary":"Routing with machine learning",'
                '"evidence_supported_judgements":["Evidence mentions routing."],'
                '"reasonable_inferences":["The method should be narrowed."],'
                '"gaps":["Data source is unclear."],'
                '"risks":["Scope may be broad."],'
                '"next_questions":["What dataset will be used?"]}'
            )
        elif "guided reading coach" in prompt:
            yield (
                '{"feedback":"The research object is identified.",'
                '"evidence_notes":["Page-bound evidence was used."],'
                '"next_question":"What method does the paper use?",'
                '"completed":false,'
                '"learning_summary":""}'
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


class ApiFakeOcrService:
    def ocr_image(self, image_path):
        return f"OCR evidence from {image_path.stem}"


class ApiFakePdfDownloader:
    def download(self, url, destination, max_bytes):
        del url, max_bytes
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "downloaded vehicle routing evidence")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(document.tobytes())
        document.close()


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
        ocr_service=ApiFakeOcrService(),
        pdf_downloader=ApiFakePdfDownloader(),
    )
    with TestClient(app) as test_client:
        yield test_client
