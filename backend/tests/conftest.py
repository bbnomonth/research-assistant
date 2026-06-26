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
        full_prompt = "\n".join(item.get("content", "") for item in messages)
        if "英文检索式" in prompt:
            yield '{"english_query":"vehicle routing"}'
        elif "候选文献" in prompt:
            yield (
                '[{"arxiv_id":"2401.00001","reason":"高度相关",'
                '"purpose_labels":["方法相似"]}]'
            )
        elif "完整全面的论文解读" in prompt:
            yield "# paper.pdf 论文解读\n\n第 1 页内容显示该论文讨论机器学习与车辆路径问题。"
        elif "中文对比报告" in prompt:
            yield "# 论文对比报告\n\n这些论文都围绕车辆路径优化展开，方法证据存在差异。"
        elif "结构化论文框架卡片" in full_prompt:
            yield (
                '{"title_suggestion":"基于机器学习的车辆路径优化研究",'
                '"research_questions":["如何提升路径优化效率？"],'
                '"core_logic":"从问题界定到算法设计再到实验验证。",'
                '"chapter_structure":[{"chapter":"第一章",'
                '"title":"绪论","key_points":"研究背景与问题提出"}],'
                '"research_methods":["算法设计","对比实验"],'
                '"innovations":["面向具体场景的模型改进"],'
                '"dialogue_summary":"用户已明确研究方向，并形成初步框架。"}'
            )
        elif "选题方案 Markdown" in full_prompt:
            yield (
                "# 选题方案\n\n"
                "## 方向一：基于强化学习的城市配送路径优化\n\n"
                "**核心研究问题**：如何利用强化学习算法提升多约束城市配送路径的求解效率与解质量？\n\n"
                "**推荐依据**：学生具备运筹学基础，掌握算法设计能力，数据资源可通过企业合作或公开数据集获取，研究兴趣在智能优化方向。\n\n"
                "## 方向二：考虑碳排放的绿色车辆路径问题\n\n"
                "**核心研究问题**：如何将碳排放约束纳入车辆路径优化模型，平衡成本与环保目标？\n\n"
                "**推荐依据**：与碳中和政策热点契合，文献基础扎实，方法以多目标优化为主，风险较低。\n\n"
                "---\n\n"
                "## 整体选型建议\n\n"
                "若侧重理论深度，优先选方向一；若偏重实践落地，选方向二。"
            )
        elif "文献卡片" in prompt:
            yield (
                '{"research_topic":"Vehicle routing",'
                '"research_question":"How is ML used in routing?",'
                '"method":"Review of vehicle routing methods",'
                '"contribution":"Provides structured analysis of routing literature",'
                '"risks":["Evidence limited to 5 papers","Abstract only"]}'
            )
        elif "对比" in prompt or "comparison" in prompt.lower() or "Paper Comparison" in prompt:
            yield (
                '{"overview":"Both papers study vehicle routing optimization.",'
                '"findings":[{"dimension":"Method",'
                '"summary":"They use different routing methods.",'
                '"evidence_notes":["Evidence is page-bound."]}],'
                '"transferable_insights":["Compare method fit before reuse."],'
                '"risks":["Evidence is limited"]}'
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
