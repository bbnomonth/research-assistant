"""选题导师服务 — 参照 FrameworkBuilder 模式：纯流追问 + 卡片整理."""
from __future__ import annotations

import time
from typing import AsyncIterator, Dict, List

from sqlalchemy.orm import Session

from research_agent.db.models import Artifact
from research_agent.repositories.artifacts import ArtifactRepository
from research_agent.services.model_call_logging import record_model_call
from research_agent.services.model_gateway import ModelGateway, collect_chat


# ── Prompts ───────────────────────────────────────────────────────────────────

_TOPIC_GUIDANCE_SYSTEM = """你是擅长用苏格拉底式引导的高水平研究生选题导师。全程遵循「先启发梳理，后精准交付」的逻辑：
- 前期通过递进式提问，引导学生自主梳理自身条件与诉求，不直接灌输结论、不强行投喂方向；
- 仅当你充分掌握学生信息、对适配判断拥有 95% 以上信心时，再输出最终选题方案。

第一阶段：启发式信息收集
通过开放式提问逐步摸清核心信息，单次回复仅提 1 个问题，循序渐进，不堆砌、不跳跃。需覆盖的核心维度：
  - 本科以及研究生专业背景、能力基础
  - 研究兴趣
  - 成果诉求
  - 可支配的科研资源
  - 风险接受度
  - 导师有无偏好或不做严格要求
还可以根据具体情况，增加其它维度的询问以增强判断质量。

提问原则：承接学生的回答再延伸问题，引导其自我澄清模糊认知、发现潜在矛盾，全程中立客观，不做好坏评判，不替学生做决策。

第二阶段：选题方案交付
信息充分且信心达标后，输出 3-5 个高质量研究方向，每个方向按以下结构呈现：
  - 方向名称：精准点明研究领域与核心切入点
  - 核心研究问题：用 1-2 句话说明拟解决的关键科学 / 应用问题
  - 推荐依据：结合学生的能力、兴趣、资源、职业规划，说明该方向的适配性与优势

全部选题输出后，补充一段整体选型建议，告知学生按不同核心优先级该如何选择。

请用中文回答。"""

_TOPIC_CARD_SYSTEM = """你是一名学术成果整理助手。下面是一段研究生与选题导师之间的对话。请只基于对话内容，整理为一份结构清晰的选题方案 Markdown，用于保存到研究项目成果中。

要求：
- 直接输出 Markdown 格式的选题方案，不要任何前言或解释；
- 内容应覆盖：3-5 个研究方向（每个含方向名称、核心研究问题、推荐依据），以及整体选型建议；
- 信息不足之处如实写"待补充"，不要编造。

请用中文回答。"""


# ── Final-plan detection (kept for /topic/card endpoint guard) ────────────────

_FINAL_PLAN_MARKERS = (
    "方向名称",
    "核心研究问题",
    "推荐依据",
    "整体选型建议",
    "推荐",
    "适配性",
    "方向",
)


def is_topic_guidance_final_plan(text: str) -> bool:
    """Return True when text looks like a completed topic guidance plan."""
    normalized = text.strip()
    if len(normalized) < 150:
        return False
    marker_hits = sum(1 for m in _FINAL_PLAN_MARKERS if m in normalized)
    return marker_hits >= 3


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_transcript(messages: List[dict]) -> str:
    lines = []
    for item in messages:
        role = item.get("role", "")
        if role == "system":
            continue
        label = "用户" if role == "user" else "选题导师"
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{label}：{content}")
    return "\n\n".join(lines)[-12000:]


# ── Service ───────────────────────────────────────────────────────────────────

class TopicGuidanceService:
    def __init__(self, db: Session, model_gateway: ModelGateway) -> None:
        self.db = db
        self.gateway = model_gateway

    async def stream_guidance(
        self,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> AsyncIterator[str]:
        """纯流：直接 yield LLM token，不做内部 artifact 创建。

        与 FrameworkBuilder 保持一致的接口。
        """
        messages = [
            {"role": "system", "content": _TOPIC_GUIDANCE_SYSTEM},
            *history[-20:],
            {"role": "user", "content": user_input},
        ]

        started = time.perf_counter()
        try:
            async for token in self.gateway.stream_chat(messages):
                yield token
        except Exception as exc:
            record_model_call(
                self.db,
                "topic_guidance_chat",
                self.gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

        record_model_call(
            self.db,
            "topic_guidance_chat",
            self.gateway.model_name,
            started,
            0,
            True,
        )

    async def summarize_to_markdown(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """将已有对话整理为 Markdown 选题卡片（供 /topic/card 端点调用）。"""
        transcript = _format_transcript(messages)
        started = time.perf_counter()
        try:
            response = await collect_chat(
                self.gateway,
                [
                    {"role": "system", "content": _TOPIC_CARD_SYSTEM},
                    {"role": "user", "content": f"对话内容：\n{transcript}"},
                ],
            )
        except Exception as exc:
            record_model_call(
                self.db,
                "topic_guidance_card",
                self.gateway.model_name,
                started,
                0,
                False,
                exc,
            )
            raise

        record_model_call(
            self.db,
            "topic_guidance_card",
            self.gateway.model_name,
            started,
            0,
            True,
        )
        return response.strip()
