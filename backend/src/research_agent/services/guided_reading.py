from dataclasses import dataclass
import json
import time
from collections.abc import AsyncIterator
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact, Paper
from research_agent.repositories.paper_chunks import EvidenceResult, PaperChunkRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway, collect_chat


_GUIDED_READING_SYSTEM = """你是一名水平高超的资深教授。你的任务是使用苏格拉底式提问法，带领研究生逐步精读学术论文，帮助其理解论文、质疑论文，并将论文中的思想迁移到自己的研究中，当学生已经将绝大部分关键问题 80% 的程度回答正确以后，你再完整地进行最终讲解。

你的核心目标不是直接替学生总结论文，而是通过循序渐进的问题，引导学生自己完成理解、分析、批判和迁移。

请遵守以下原则：
1. 以提问为主，讲解为辅。
每次优先提出 1 个关键问题，不要一次性抛出太多问题。
2. 始终要求回到原文。
当学生给出判断时，引导其说明依据来自论文中的哪一段、哪张图、哪张表、哪个公式或哪个实验结果。
3. 按照论文精读逻辑逐步推进，请根据具体情况选择几个问题作为关键进行适当深挖以及和学生深度讨论。
一般可以次关注，可根据具体情况增加或删减提问：
* 这篇论文研究什么问题？
* 作者为什么认为这个问题重要？
* 已有研究有什么不足？
* 作者提出了什么方法、模型、框架或观点？
* 论文的证据是否支持结论？
* 这篇论文有什么创新？
* 这篇论文有什么局限？
4. 根据学生回答灵活追问。
如果学生理解不清楚，追问概念、依据和逻辑。
如果学生已经理解基本内容，继续引导其分析研究设计、证据质量、创新性、局限性和可迁移价值。
5. 不要编造论文内容。
如果学生没有提供论文全文、摘要、截图或关键段落，不要虚构作者观点、实验结果或结论。应先让学生提供必要材料。
6. 保持导师式风格。
语气应启发、严谨、耐心，不要直接否定学生，而是通过问题帮助学生发现理解中的漏洞。
7. 输出方式保持简洁完整。
当学生已经充分理解某一部分时，可以给出简短总结，并继续提出下一个问题。
你的最终目标是帮助学生从“读懂一篇论文”，逐步发展出独立的学术阅读能力、批判性判断能力和研究设计能力。"""


_GUIDED_READING_CARD_SYSTEM = """你是一名严谨的学术阅读成果整理助手。下面是一段研究生与论文精读导师围绕同一篇论文的对话。

请只基于对话内容和给定论文信息，整理为一张可保存到研究项目成果中的中文 Markdown 精读卡片。

要求：
- 直接输出 Markdown，不要前言、寒暄或解释；
- 信息不足之处写“待补充”，不要编造论文没有出现的实验、结论或数据；
- 优先保留导师最终讲解中的核心判断、学生已澄清的理解，以及仍需回原文核查的问题；
- 内容建议包括：论文题目、研究问题、核心方法/模型、关键证据、创新点、局限、可迁移启发、后续精读清单。
"""


_FINAL_READING_MARKERS = (
    "最终讲解",
    "最终总结",
    "完整讲解",
    "完整总结",
    "精读总结",
    "阅读总结",
    "总结如下",
    "综上",
    "现在我完整地讲解",
    "下面给出完整讲解",
    "已经完成主要精读",
    "已经完成了主要精读",
    "final summary",
    "final explanation",
)

_FINAL_READING_SECTIONS = (
    "研究问题",
    "核心方法",
    "关键证据",
    "创新点",
    "局限",
    "可迁移",
    "后续精读",
    "research question",
    "method",
    "evidence",
    "contribution",
    "limitation",
)


def _looks_like_final_reading_output(text: str) -> bool:
    normalized = " ".join((text or "").casefold().split())
    if not normalized:
        return False
    if any(marker.casefold() in normalized for marker in _FINAL_READING_MARKERS):
        return True
    section_hits = sum(
        1 for marker in _FINAL_READING_SECTIONS if marker.casefold() in normalized
    )
    return section_hits >= 4 and len(normalized) >= 240


def _format_transcript(messages: List[Dict[str, str]]) -> str:
    lines = []
    for item in messages:
        role = item.get("role", "")
        if role == "system":
            continue
        label = "用户" if role == "user" else "精读导师"
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{label}：{content}")
    return "\n\n".join(lines)[-14000:]


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
        return GuidedReadingResult(
            turn=turn,
            evidence=evidence,
            artifact=None,
        )

    async def stream_guide(
        self,
        project_id: str,
        paper_id: str,
        user_input: str,
        history: List[Dict[str, str]],
    ) -> AsyncIterator[Dict]:
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

        pieces: List[str] = []
        async for token in self._stream_turn_text(
            paper=paper,
            user_input=user_input,
            history=history[-12:],
            evidence=evidence,
            stage=stage,
        ):
            pieces.append(token)
            yield {"type": "token", "content": token}

        turn = self._turn_from_text("".join(pieces), stage, evidence)
        yield {
            "type": "done",
            "turn": turn,
            "evidence": evidence,
            "artifact": None,
        }

    async def summarize_to_markdown(
        self,
        paper: Paper,
        messages: List[Dict[str, str]],
    ) -> str:
        transcript = _format_transcript(messages)
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.model_gateway,
                [
                    {"role": "system", "content": _GUIDED_READING_CARD_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"论文题目：{paper.title}\n"
                            f"论文摘要：{paper.abstract[:2000]}\n\n"
                            f"精读对话：\n{transcript}"
                        ),
                    },
                ],
            )
        except Exception as exc:
            record_model_call(
                self.db,
                "guided_reading_card",
                self.model_gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise
        record_model_call(
            self.db,
            "guided_reading_card",
            self.model_gateway.model_name,
            started,
            0,
            True,
        )
        markdown = response.strip()
        if markdown:
            return markdown
        return (
            f"# {paper.title} 精读卡片\n\n"
            "## 对话摘要\n\n待补充\n\n"
            "## 后续精读清单\n\n- 回到原文核查关键证据\n"
        )

    async def _build_turn(
        self,
        paper: Paper,
        user_input: str,
        history: List[Dict[str, str]],
        evidence: List[EvidenceResult],
        stage: str,
    ) -> GuidedReadingTurn:
        pieces = [
            token
            async for token in self._stream_turn_text(
                paper=paper,
                user_input=user_input,
                history=history,
                evidence=evidence,
                stage=stage,
            )
        ]
        return self._turn_from_text("".join(pieces), stage, evidence)

    def _build_messages(
        self,
        paper: Paper,
        user_input: str,
        history: List[Dict[str, str]],
        evidence: List[EvidenceResult],
        stage: str,
    ) -> List[Dict[str, str]]:
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
        user_prompt = (
            f"论文标题：{paper.title}\n"
            f"当前内部阅读阶段：{stage}（{self.STAGE_LABELS.get(stage, stage)}，仅供你选择追问重点，不要机械声明阶段）\n"
            f"论文原文片段：{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"研究者本次输入：{user_input}\n\n"
            "请基于论文原文片段和对话历史进行导师式回应。优先提出 1 个关键追问；"
            "如果需要讲解，只做必要铺垫，并要求学生回到原文证据。"
        )
        return [
            {"role": "system", "content": _GUIDED_READING_SYSTEM},
            *history,
            {"role": "user", "content": user_prompt},
        ]

    async def _stream_turn_text(
        self,
        paper: Paper,
        user_input: str,
        history: List[Dict[str, str]],
        evidence: List[EvidenceResult],
        stage: str,
    ) -> AsyncIterator[str]:
        messages = self._build_messages(
            paper=paper,
            user_input=user_input,
            history=history,
            evidence=evidence,
            stage=stage,
        )
        started = time.perf_counter()
        try:
            async for token in self.model_gateway.stream_chat(messages):
                yield token
            record_model_call(
                self.db,
                "guided_reading",
                self.model_gateway.model_name,
                started,
                0,
                True,
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

    def _turn_from_text(
        self,
        text: str,
        stage: str,
        evidence: List[EvidenceResult],
    ) -> GuidedReadingTurn:
        cleaned = text.strip()
        if not cleaned:
            return self._fallback_turn(stage, evidence, "")
        evidence_notes = [
            f"第 {item.page_number} 页：{item.text[:120]}"
            for item in evidence[:3]
        ]
        completed = stage == "complete" or _looks_like_final_reading_output(cleaned)
        return GuidedReadingTurn(
            feedback=cleaned,
            evidence_notes=evidence_notes,
            next_question="",
            completed=completed,
            learning_summary=cleaned if completed else "",
            socratic_stage=stage,
        )

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
