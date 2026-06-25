from dataclasses import dataclass
import json
import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact, Paper
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.repositories.paper_chunks import EvidenceResult, PaperChunkRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway
from research_agent.services.structured_output import validate_structured


class GuidedReadingTurn(BaseModel):
    feedback: str = ""  # 苏格拉底式反馈
    evidence_notes: List[str] = Field(default_factory=list)
    next_question: str = ""  # 下一个苏格拉底追问
    completed: bool = False
    learning_summary: str = ""  # 学习总结
    socratic_stage: str = ""  # 当前引导阶段: intro/question/method/contribution/limitations/complete


@dataclass(frozen=True)
class GuidedReadingResult:
    turn: GuidedReadingTurn
    evidence: List[EvidenceResult]
    artifact: Optional[Artifact] = None

    @property
    def evidence_pages(self) -> List[int]:
        pages = []
        for item in self.evidence:
            if item.page_number not in pages:
                pages.append(item.page_number)
        return pages


class GuidedReadingService:
    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.model_gateway = model_gateway

    async def guide(
        self,
        project_id: str,
        paper_id: str,
        user_input: str,
        history: List[Dict[str, str]],
    ) -> GuidedReadingResult:
        paper = self.db.get(Paper, paper_id)
        if paper is None:
            raise LookupError("paper not found")
        if paper.project_id != project_id:
            raise ValueError("paper does not belong to project")

        evidence = PaperChunkRepository(self.db).list_for_paper(
            paper_id,
            limit=8,
        )
        if not evidence:
            raise ValueError("paper has no parsed evidence")

        turn = await self._build_turn(
            paper=paper,
            user_input=user_input,
            history=history[-12:],
            evidence=evidence,
        )
        artifact = None
        if turn.completed:
            artifact = self._create_artifact(paper, turn, evidence)
        return GuidedReadingResult(
            turn=turn,
            evidence=evidence,
            artifact=artifact,
        )

    async def _build_turn(
        self,
        paper: Paper,
        user_input: str,
        history: List[Dict[str, str]],
        evidence: List[EvidenceResult],
    ) -> GuidedReadingTurn:
        payload = [
            {
                "chunk_id": item.chunk_id,
                "page": item.page_number,
                "section": item.section,
                "text": item.text[:1200],
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        prompt = (
            "你是一位循循善诱的苏格拉底式导师，正在引导研究者精读一篇学术论文。用中文回答。\n"
            "你的职责：通过连续追问，帮助研究者深入理解论文，而非直接给出答案。\n"
            "每次回复格式：先给予积极肯定，再基于论文原文提出1-2个追问式问题，引导研究者思考。\n"
            "如果研究者回答充分，则过渡到下一个维度。\n"
            "引导维度顺序：研究问题（核心问题是什么）→ 研究方法（如何验证假设）→ 贡献与创新（突破了什么）→ 研究局限（有何不足）→ 总结。\n"
            "只能使用提供的论文原文证据，不要编造信息。返回 JSON：\n"
            "feedback：本轮苏格拉底反馈（1-3句话，肯定+追问）\n"
            "evidence_notes：引用原文的证据笔记（列出页码和关键摘录）\n"
            "next_question：下一个苏格拉底追问（1个问题）\n"
            "completed：是否完成全部维度（当5个维度都引导完毕后为 true）\n"
            "learning_summary：本次精读的学习总结（1-3句话）\n"
            "socratic_stage：当前维度（intro/question/method/contribution/limitations/complete）\n"
            f"\n论文标题：{paper.title}\n"
            f"\n对话历史：{json.dumps(history, ensure_ascii=False)}\n"
            f"\n研究者本次回答：{user_input}\n"
            f"\n论文原文证据：{json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = GuidedReadingTurn(
            feedback="结合原文再思考一下：这项研究试图回答的核心问题是什么？",
            next_question="请结合论文第X页的内容，说明作者如何定义和验证其核心假设。",
            socratic_stage="question",
        )
        started = time.perf_counter()
        try:
            result = await validate_structured(
                gateway=self.model_gateway,
                prompt=prompt,
                validator=GuidedReadingTurn.model_validate,
                fallback=fallback,
            )
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                result.retries,
                True,
            )
            return result.value
        except Exception as exc:
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

    def _create_artifact(
        self,
        paper: Paper,
        turn: GuidedReadingTurn,
        evidence: List[EvidenceResult],
    ) -> Artifact:
        evidence_content = [
            {
                "chunk_id": item.chunk_id,
                "page_number": item.page_number,
                "section": item.section,
                "is_ocr": item.is_ocr,
            }
            for item in evidence
        ]
        evidence_lines = "\n".join(
            f"- Page {item.page_number}: {item.text[:180]}"
            for item in evidence
        )
        notes = "\n".join(
            f"- {item}" for item in turn.evidence_notes
        ) or "- 无"
        markdown = (
            f"# {paper.title} 精读笔记\n\n"
            f"## 学习总结\n\n{turn.learning_summary}\n\n"
            f"## 导师反馈\n\n{turn.feedback}\n\n"
            f"## 证据笔记\n\n{notes}\n\n"
            f"## 原文证据\n\n{evidence_lines}\n"
        )
        return ArtifactRepository(self.db).create_artifact(
            project_id=paper.project_id,
            artifact_type="guided_reading_note",
            title=f"精读笔记：{paper.title[:30]}",
            content={
                **turn.model_dump(),
                "paper_id": paper.id,
                "evidence": evidence_content,
            },
            markdown=markdown,
        )
