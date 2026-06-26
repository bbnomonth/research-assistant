"""选题导师服务 — 苏格拉底式多轮对话 + 方案生成."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from research_agent.db.models import Artifact
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway, collect_chat


# ── Schema ────────────────────────────────────────────────────────────────────

class ChapterOutline(BaseModel):
    chapter: str
    title: str
    focus: str


class TopicGuidancePlan(BaseModel):
    recommended_title: str = Field(description="推荐论文题目")
    alternative_titles: List[str] = Field(description="备选题目，2-3个")
    core_research_question: str = Field(description="核心研究问题")
    research_background: str = Field(description="研究背景")
    research_object: str = Field(description="研究对象与范围")
    theory_foundation: str = Field(description="理论基础")
    research_method: str = Field(description="研究方法")
    data_source: str = Field(description="数据来源")
    innovation_points: List[str] = Field(description="创新点，2-3个")
    feasibility_analysis: str = Field(description="可行性分析")
    outline: List[ChapterOutline] = Field(description="论文框架")
    risks_and_mitigation: str = Field(description="潜在风险与规避方案")


@dataclass(frozen=True)
class TopicGuidanceResult:
    artifact: Artifact


# ── Prompts ───────────────────────────────────────────────────────────────────

_TOPIC_GUIDANCE_SYSTEM = """你是一位高水平的研究选题导师，擅长苏格拉底式提问法。

你的职责是通过连续追问，帮助学生从模糊的想法逐步收敛，最终产出一个具体、可操作、有创新性的论文选题方案。

每次只问 1 个最关键的问题，不要一次问多个问题。
每次提问前，先简要（1-2句话）判断用户当前回答中最值得深挖的点。
话题推进维度（按需引入，不必每次都覆盖）：
  1. 研究兴趣与方向
  2. 研究对象与范围
  3. 具体研究问题
  4. 文献基础与相关工作
  5. 理论价值与实践意义
  6. 数据来源与可行性
  7. 研究方法与技术路线
  8. 创新点与贡献预期

引导策略：
- 想法太宽泛 → 引导收缩到具体问题
- 想法太技术化 → 追问要解决什么学术/实际问题
- 想法太宏大 → 追问具体数据来源、方法和时间范围
- 有明确想法 → 追问创新点、可行性和理论深度

当且仅当你对用户的选题已有充分把握（覆盖研究对象、问题、方法、数据、创新点中至少 5 项），才输出完整选题方案。

输出格式（只需按要求输出，不要额外说明）：
- 如果继续追问：直接输出追问内容（纯文本，正常对话语气）
- 如果准备输出方案：以【选题方案】开头，后接纯文本选题方案，按以下标题组织内容：
  【推荐题目】→ 【备选题目】→ 【核心问题】→ 【研究背景】→ 【研究对象】→ 【理论基础】→ 【研究方法】→ 【数据来源】→ 【创新点】→ 【可行性分析】→ 【论文框架】→ 【风险与规避】

请用中文回答。"""

_PLAN_STRUCTURE_PROMPT = """你是一个学术成果整理专家。请将以下论文选题方案整理为严格的 JSON 格式。

只返回 JSON，不要任何其他内容。

JSON 必须包含以下字段（字段名必须完全一致）：
- recommended_title: 字符串，推荐论文题目
- alternative_titles: 字符串数组，2-3个备选题目
- core_research_question: 字符串，核心研究问题
- research_background: 字符串，研究背景
- research_object: 字符串，研究对象与范围
- theory_foundation: 字符串，理论基础
- research_method: 字符串，研究方法
- data_source: 字符串，数据来源
- innovation_points: 字符串数组，2-3个创新点
- feasibility_analysis: 字符串，可行性分析
- outline: 对象数组，每项含 chapter（章号，如"第一章"）、title（章标题）、focus（本章写作重点）
- risks_and_mitigation: 字符串，潜在风险与规避方案

原始选题方案内容：
{raw_plan}

只返回 JSON。"""


# ── Marker detection ──────────────────────────────────────────────────────────

_PLAN_MARKER = "【选题方案】"


def _extract_plan(text: str) -> str | None:
    """Return plan text after the marker, or None if no marker found."""
    idx = text.find(_PLAN_MARKER)
    if idx == -1:
        return None
    return text[idx + len(_PLAN_MARKER) :].strip()


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_plan_md(plan: TopicGuidancePlan, plan_text: str) -> str:
    outline_lines = []
    for ch in plan.outline:
        outline_lines.append(f"**{ch.chapter} {ch.title}**")
        outline_lines.append(f"{ch.focus}")
        outline_lines.append("")

    return f"""# {plan.recommended_title}

## 备选题目
{chr(10).join(f"- {t}" for t in plan.alternative_titles)}

## 核心问题
{plan.core_research_question}

## 研究背景
{plan.research_background}

## 研究对象
{plan.research_object}

## 理论基础
{plan.theory_foundation}

## 研究方法
{plan.research_method}

## 数据来源
{plan.data_source}

## 创新点
{chr(10).join(f"- {p}" for p in plan.innovation_points)}

## 可行性分析
{plan.feasibility_analysis}

## 论文框架
{chr(10).join(outline_lines)}

## 风险与规避
{plan.risks_and_mitigation}

---

*本方案由选题导师经多轮苏格拉底对话生成，仅供参考。*
"""


# ── Service ───────────────────────────────────────────────────────────────────

class TopicGuidanceService:
    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.gateway = model_gateway

    async def stream_guidance(
        self,
        project_id: str,
        session_id: str,
        user_input: str,
        history: List[Dict[str, str]],
    ) -> AsyncIterator[Dict]:
        """Run the full topic guidance session, yielding token dicts.

        Detects 【选题方案】 marker during streaming, then calls the
        second LLM to structure the plan and creates an Artifact.
        """
        messages = [
            {"role": "system", "content": _TOPIC_GUIDANCE_SYSTEM},
            *history[-20:],
            {"role": "user", "content": user_input},
        ]

        started = time.perf_counter()
        full_text: List[str] = []
        plan_detected = False
        plan_raw_text: str | None = None
        question_text: str | None = None

        try:
            async for token in self.gateway.stream_chat(messages):
                full_text.append(token)

                if not plan_detected:
                    current = "".join(full_text)
                    if _PLAN_MARKER in current:
                        plan_detected = True
                        question_part, plan_part = current.split(_PLAN_MARKER, 1)
                        question_text = question_part.strip()
                        plan_raw_text = plan_part.strip()
                        yield {"type": "token", "content": question_text}
                        yield {"type": "done_question", "content": question_text}
                        break
                    yield {"type": "token", "content": token}

            if not plan_detected:
                yield {"type": "done_question", "content": "".join(full_text)}
                record_model_call(
                    self.db,
                    "topic_guidance",
                    self.gateway.model_name,
                    started,
                    0,
                    True,
                )
                return

            plan_text = plan_raw_text or ""
            if not plan_text:
                record_model_call(
                    self.db,
                    "topic_guidance",
                    self.gateway.model_name,
                    started,
                    0,
                    True,
                )
                yield {"type": "plan_error", "content": "方案内容为空，无法生成结构化成果。"}
                return

            plan_obj = await self._structure_plan(plan_text, started)
            artifact = self._save_artifact(project_id, plan_obj, plan_text)

            yield {
                "type": "artifact",
                "artifact_id": artifact.id,
                "artifact_type": "topic_guidance_plan",
                "title": plan_obj.recommended_title,
            }

        except Exception as exc:
            record_model_call(
                self.db,
                "topic_guidance",
                self.gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            yield {"type": "error", "message": "选题导师暂时不可用，请稍后重试。"}

    async def _structure_plan(
        self,
        raw_plan: str,
        started: float,
    ) -> TopicGuidancePlan:
        prompt = _PLAN_STRUCTURE_PROMPT.format(raw_plan=raw_plan[: 8_000])
        response = await collect_chat(
            self.gateway,
            [{"role": "user", "content": prompt}],
        )

        try:
            data = json.loads(response.strip())
            return TopicGuidancePlan.model_validate(data)
        except Exception:
            try:
                match = re.search(r"\{.*\}", response, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    return TopicGuidancePlan.model_validate(data)
            except Exception:
                pass
            return self._fallback_plan(raw_plan)

    def _fallback_plan(self, raw_plan: str) -> TopicGuidancePlan:
        title = ""
        for line in raw_plan.splitlines():
            line = line.strip()
            if line.startswith("推荐题目") or line.startswith("【推荐题目】"):
                title = line.split("→", 1)[-1].strip()
                break
        if not title:
            title = raw_plan.split("\n")[0][:100] or "选题方案"
        return TopicGuidancePlan(
            recommended_title=title,
            alternative_titles=["（备选题目待补充）"],
            core_research_question=raw_plan[:500],
            research_background="（见方案正文）",
            research_object="（见方案正文）",
            theory_foundation="（见方案正文）",
            research_method="（见方案正文）",
            data_source="（见方案正文）",
            innovation_points=["（见方案正文）"],
            feasibility_analysis="（见方案正文）",
            outline=[ChapterOutline(chapter="", title="（待补充）", focus=raw_plan[:200])],
            risks_and_mitigation="（见方案正文）",
        )

    def _save_artifact(
        self,
        project_id: str,
        plan: TopicGuidancePlan,
        plan_text: str,
    ) -> Artifact:
        markdown = _render_plan_md(plan, plan_text)
        content = plan.model_dump()
        artifact = ArtifactRepository(self.db).create_artifact(
            project_id=project_id,
            artifact_type="topic_guidance_plan",
            title=plan.recommended_title,
            content=content,
            markdown=markdown,
        )
        return artifact
