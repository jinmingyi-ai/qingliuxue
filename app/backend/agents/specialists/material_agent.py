# -*- coding: utf-8 -*-
"""Application material preparation agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, profile_goal, source_from_rag_item
from app.backend.rag.knowledge_base import build_knowledge_context
from app.backend.tools.web_tools import web_research


class MaterialAgent:
    name = "material_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = profile_goal(profile)
        knowledge = build_knowledge_context(
            "prepare",
            f"{query} {goal['country_label']} {goal['level_label']} 材料清单 推荐信 成绩单 简历 文书",
            k=3,
            filters={"country": goal["country"], "level": goal["level"]},
        )
        web = web_research("materials", query, country=goal["country"], level=goal["level"], program=goal["major"])
        checklist = self._build_checklist(goal, knowledge["results"])
        answer = self._answer(goal, checklist)
        sources = [source_from_rag_item(item, "prepare_knowledge") for item in knowledge["results"]]
        sources.append({"type": "web_research_plan", "topic": "materials", "source_hints": web["source_hints"]})
        return AgentResult(
            agent=self.name,
            task="材料准备指导",
            answer=answer,
            structured={"goal": goal, "material_checklist": checklist, "web_research": web},
            sources=sources,
            confidence=0.88 if knowledge["results"] else 0.55,
        ).to_dict()

    def _build_checklist(self, goal: dict[str, Any], knowledge_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raw = (knowledge_items[0].get("raw") if knowledge_items else {}) or {}
        required = raw.get("required_documents") or [
            "成绩单",
            "推荐信",
            "Resume/CV",
            "Personal Statement / SOP",
            "语言成绩",
        ]
        tips = raw.get("key_tips") or []
        common_issues = raw.get("common_issues_for_chinese_students") or []
        checklist = []
        for idx, doc in enumerate(required, 1):
            checklist.append(
                {
                    "item": doc,
                    "priority": "high" if idx <= 5 else "medium",
                    "owner": "用户/学校/推荐人" if "Recommendation" in doc or "推荐" in doc else "用户",
                    "suggested_timing": self._timing_for_doc(doc, goal),
                    "quality_bar": self._quality_bar(doc),
                    "risk_notes": self._risk_notes(doc, common_issues),
                }
            )
        if tips:
            checklist.append(
                {
                    "item": "材料整体质量控制",
                    "priority": "high",
                    "owner": "用户",
                    "suggested_timing": "提交前2-4周",
                    "quality_bar": "所有材料信息一致、时间线一致、成果可量化。",
                    "risk_notes": tips[:3],
                }
            )
        return checklist

    def _timing_for_doc(self, doc: str, goal: dict[str, Any]) -> str:
        text = doc.lower()
        if "recommendation" in text or "推荐" in doc:
            return "截止前至少2个月确认推荐人，截止前3-4周完成提交提醒。"
        if "transcript" in text or "成绩单" in doc:
            return "截止前1-2个月开具中英文版本并确认盖章/认证要求。"
        if "sop" in text or "statement" in text or "文书" in doc:
            return "截止前6-8周完成初稿，截止前2周定稿。"
        if "test" in text or "toefl" in text or "ielts" in text or "gre" in text:
            return "截止前至少1个月完成送分，预留补考窗口。"
        return "截止前4-6周准备，提交前统一核对。"

    def _quality_bar(self, doc: str) -> str:
        text = doc.lower()
        if "resume" in text or "cv" in text or "简历" in doc:
            return "本科1页、研究生1-2页，突出量化成果和申请相关经历。"
        if "recommendation" in text or "推荐" in doc:
            return "推荐人要能提供具体项目/课堂/研究细节，避免泛泛夸奖。"
        if "transcript" in text or "成绩单" in doc:
            return "中英文、盖章、评分说明和认证要求要一致。"
        return "内容真实、格式符合官网要求，文件名和上传版本清晰。"

    def _risk_notes(self, doc: str, common_issues: list[str]) -> list[str]:
        matched = []
        for issue in common_issues:
            if any(token in issue for token in ["成绩单", "推荐", "邮箱", "WES", "资金", "公章"]):
                matched.append(issue)
        return matched[:3] or ["以项目官网最新材料要求为准。"]

    def _answer(self, goal: dict[str, Any], checklist: list[dict[str, Any]]) -> str:
        lines = [f"{goal['country_label']} {goal['level_label']}申请材料建议按下面清单推进："]
        for item in checklist[:6]:
            lines.append(f"- {item['item']}：{item['suggested_timing']} 质量标准：{item['quality_bar']}")
        return "\n".join(lines)
