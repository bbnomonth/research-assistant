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
from research_agent.services.model_gateway import ModelGateway, collect_chat


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
    STAGE_ORDER = ("question", "method", "contribution", "limitations", "complete")
    STAGE_LABELS = {
        "intro": "阅读定位",
        "question": "研究问题",
        "method": "方法与证据",
        "contribution": "贡献与创新",
        "limitations": "局限与边界",
        "complete": "总结",
    }
    STAGE_KEYWORDS = {
        "question": (
            "abstract",
            "introduction",
            "problem",
            "objective",
            "研究问题",
            "目标",
            "摘要",
            "引言",
        ),
        "method": (
            "method",
            "methodology",
            "experiment",
            "dataset",
            "model",
            "方法",
            "实验",
            "数据",
            "模型",
        ),
        "contribution": (
            "contribution",
            "result",
            "finding",
            "performance",
            "贡献",
            "结果",
            "发现",
            "创新",
        ),
        "limitations": (
            "limitation",
            "discussion",
            "future",
            "conclusion",
            "局限",
            "讨论",
            "不足",
            "未来",
            "结论",
        ),
    }

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
        if not paper.favorited and not paper.arxiv_id.startswith("upload:"):
            raise ValueError("paper must be in the paper library before guided reading")

        stage = self._infer_stage(user_input, history)
        evidence = self._select_evidence(
            PaperChunkRepository(self.db).list_for_paper(paper_id, limit=80),
            stage=stage,
            limit=8,
        )
        if not evidence:
            raise ValueError("paper has no parsed evidence")

        turn = await self._build_turn(
            paper=paper,
            user_input=user_input,
            history=history[-12:],
            evidence=evidence,
            stage=stage,
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
        stage: str,
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
            "你是一位论文精读导师，请采用苏格拉底提问法引导研究者阅读这篇论文。"
            "请结合当前阅读阶段、对话历史和论文原文，先用简短反馈指出用户理解中值得保留或需要澄清的点，"
            "再提出一个具体、可回答的追问；追问要指向论文中的具体页码或段落线索。"
            "每次只推进一个阅读动作，避免直接替用户总结全文。"
            "如果用户只是说“带我精读/开始精读”，请先给出本阶段阅读定位，再提出第一个可执行问题。"
            "请只输出一段自然中文，不要输出 JSON、字段名、寒暄或模板化说明。\n"
            f"\n论文标题：{paper.title}\n"
            f"\n建议推进阶段：{stage}（{self.STAGE_LABELS.get(stage, stage)}）\n"
            f"\n对话历史：{json.dumps(history, ensure_ascii=False)}\n"
            f"\n研究者本次输入：{user_input}\n"
            f"\n论文原文：{json.dumps(payload, ensure_ascii=False)}"
        )
        fallback = self._fallback_turn(stage, evidence, user_input)
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.model_gateway,
                [{"role": "user", "content": prompt}],
            )
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                0,
                True,
            )
            text = response.strip()
            if not text:
                return fallback
            evidence_notes = [
                f"第 {item.page_number} 页：{item.text[:120]}"
                for item in evidence[:3]
            ]
            completed = stage == "complete"
            return GuidedReadingTurn(
                feedback=text,
                evidence_notes=evidence_notes,
                next_question="",
                completed=completed,
                learning_summary=text if completed else "",
                socratic_stage=stage,
            )
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

    def _infer_stage(
        self,
        user_input: str,
        history: List[Dict[str, str]],
    ) -> str:
        normalized = user_input.strip().casefold()
        if not history or any(word in normalized for word in ("开始", "精读", "带我")):
            return "question"
        stage_mentions = " ".join(
            item.get("content", "") for item in history[-8:]
        ).casefold()
        label_to_stage = {
            "研究问题": "method",
            "方法": "contribution",
            "贡献": "limitations",
            "创新": "limitations",
            "局限": "complete",
            "边界": "complete",
        }
        for label, next_stage in label_to_stage.items():
            if label in stage_mentions:
                return next_stage
        for stage in self.STAGE_ORDER:
            if stage != "complete" and stage in stage_mentions:
                current_index = self.STAGE_ORDER.index(stage)
                return self.STAGE_ORDER[
                    min(current_index + 1, len(self.STAGE_ORDER) - 1)
                ]
        user_turns = sum(1 for item in history if item.get("role") == "user")
        return self.STAGE_ORDER[min(user_turns, len(self.STAGE_ORDER) - 1)]

    def _select_evidence(
        self,
        candidates: List[EvidenceResult],
        stage: str,
        limit: int,
    ) -> List[EvidenceResult]:
        if not candidates:
            return []
        keywords = self.STAGE_KEYWORDS.get(stage, ())
        first_page = min(item.page_number for item in candidates)
        selected = [item for item in candidates if item.page_number == first_page]
        if keywords:
            selected.extend(
                item for item in candidates if self._matches_keywords(item, keywords)
            )
        selected.extend(candidates)
        deduped = []
        seen = set()
        for item in selected:
            if item.chunk_id in seen:
                continue
            deduped.append(item)
            seen.add(item.chunk_id)
            if len(deduped) == limit:
                break
        return deduped

    @staticmethod
    def _matches_keywords(item: EvidenceResult, keywords) -> bool:
        haystack = f"{item.section}\n{item.text}".lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    def _fallback_turn(
        self,
        stage: str,
        evidence: List[EvidenceResult],
        user_input: str,
    ) -> GuidedReadingTurn:
        item = evidence[0]
        stage_label = self.STAGE_LABELS.get(stage, "研究问题")
        notes = [
            f"第 {e.page_number} 页：{e.text[:120]}"
            for e in evidence[:3]
        ]
        opening = (
            "先从论文的研究问题入手。"
            if not user_input.strip() or "精读" in user_input
            else "你的回答可以作为初步理解，但还需要回到原文定位证据。"
        )
        return GuidedReadingTurn(
            feedback=(
                f"{opening} 当前阶段是“{stage_label}”，建议先阅读第 "
                f"{item.page_number} 页附近的表述，标出作者提出问题、假设或论证对象的句子。"
            ),
            evidence_notes=notes,
            next_question=(
                f"请基于第 {item.page_number} 页的原文，用一句话说明作者在"
                f"“{stage_label}”上最想解决什么问题。"
            ),
            completed=stage == "complete",
            learning_summary="" if stage != "complete" else "已完成主要精读阶段，请复核证据笔记。",
            socratic_stage=stage,
        )

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
