# -*- coding: utf-8 -*-
"""Real-case route recommendation agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, goal_from_query, query_focus_line, source_from_rag_item, web_source_from_result
from app.backend.rag.retriever import build_rag_context
from app.backend.tools.web_tools import web_research


class CaseRecommendationAgent:
    name = "case_recommendation_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, k: int = 5, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = goal_from_query(query, profile)
        filters = {
            "country": goal["country"],
            "level": goal["level"],
            "major": goal["major"],
            "gpa": goal.get("gpa"),
            "work_years": goal.get("work_years"),
        }
        rag_query = self._compose_query(query, goal)
        rag = build_rag_context(rag_query, k=k, filters=filters)
        cases = rag.get("cases") or []
        recommendations = self._recommendations_from_cases(cases, goal)
        web = web_research("case", query, country=goal["country"], level=goal["level"], program=goal["major"])
        answer = self._answer(query, recommendations, goal, cases, web)
        sources = [source_from_rag_item(item, "case_rag") for item in cases]
        sources.append(web_source_from_result(web, "case"))

        return AgentResult(
            agent=self.name,
            task="基于真实案例推荐",
            answer=answer,
            structured={
                "goal": goal,
                "recommended_routes": recommendations,
                "rag_query": rag_query,
                "case_count": len(cases),
                "rag_support": self._rag_support(cases),
                "web_research": web,
            },
            sources=sources,
            confidence=0.9 if cases else 0.45,
        ).to_dict()

    def _compose_query(self, query: str, goal: dict[str, Any]) -> str:
        parts = [
            query,
            f"{goal['country_label']} {goal['level_label']} {goal['major']}",
        ]
        if goal.get("gpa"):
            parts.append(f"GPA {goal['gpa']}")
        if goal.get("percentage_score"):
            parts.append(f"百分制成绩 {goal['percentage_score']}")
        if goal.get("work_years"):
            parts.append(f"{goal['work_years']}年工作经验")
        if goal.get("preferences"):
            parts.append("偏好 " + " ".join(goal["preferences"]))
        if goal.get("budget"):
            budget = goal["budget"]
            parts.append("预算 " + (" ".join(str(item) for item in budget) if isinstance(budget, list) else str(budget)))
        return "；".join(part for part in parts if part)

    def _recommendations_from_cases(self, cases: list[dict[str, Any]], goal: dict[str, Any]) -> list[dict[str, Any]]:
        tiers = ["冲刺参考", "重点匹配", "稳妥保底", "补充案例", "补充案例"]
        recommendations = []
        for idx, item in enumerate(cases):
            meta = item.get("metadata") or {}
            raw = item.get("raw_profile") or {}
            recommendations.append(
                {
                    "tier": tiers[min(idx, len(tiers) - 1)],
                    "case_id": meta.get("profile_id"),
                    "student": meta.get("name"),
                    "country": meta.get("country"),
                    "level": meta.get("level"),
                    "final_choice": meta.get("final_choice"),
                    "admitted_schools": meta.get("admitted_schools") or [],
                    "why_similar": item.get("reasons") or [],
                    "strategies_to_borrow": raw.get("key_strategies") or [],
                    "lessons": raw.get("lessons") or [],
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "tier": "初步方向",
                    "case_id": None,
                    "student": None,
                    "country": goal["country"],
                    "level": goal["level"],
                    "final_choice": None,
                    "admitted_schools": [],
                    "why_similar": ["当前相似案例还不够强，需要放宽条件或补充用户信息。"],
                    "strategies_to_borrow": ["先明确国家、阶段、专业、GPA、语言和经历。"],
                    "lessons": [],
                }
            )
        return recommendations

    def _rag_support(self, cases: list[dict[str, Any]]) -> str:
        if len(cases) >= 4:
            return "strong"
        if len(cases) >= 2:
            return "medium"
        if cases:
            return "weak"
        return "none"

    def _answer(
        self,
        query: str,
        recommendations: list[dict[str, Any]],
        goal: dict[str, Any],
        cases: list[dict[str, Any]],
        web: dict[str, Any],
    ) -> str:
        top = recommendations[:3]
        lines = [
            f"我按 {goal['country_label']} {goal['level_label']} {goal['major']} 的方向，先选了最接近你背景的真实案例路线。"
        ]
        focus = query_focus_line(
            query,
            ["香港", "新加坡", "就业", "澳洲", "澳大利亚", "IT", "GPA", "选校", "预算", "取舍", "机器人", "美国", "规划"],
            "我会把这些放进路线分层和风险判断里。",
        )
        if focus:
            lines.append(focus)
        if "转" in goal["major"].lower() or goal["major"] == "Computer Science":
            lines.append(
                "如果你是转专业或背景不完全匹配，定位学校时重点不是硬凑名校，而是先把项目分成冲刺、重点匹配和稳妥保底三层，并把风险放在先修课、语言、项目匹配度和文书解释上。"
            )
        if len(cases) < 3:
            lines.append(
                "但这个方向的相似案例还不算厚，我建议同步用项目官网、课程页和就业数据补齐判断。"
            )
        for item in top:
            school = item.get("final_choice") or "待定项目"
            strategies = "；".join(item.get("strategies_to_borrow") or []) or "参考其申请主线和材料组织方式"
            lines.append(f"{item['tier']}: 参考 {item.get('student') or '相似同学'} -> {school}。可借鉴: {strategies}")
        lines.append("官方核对重点：" + "；".join(web.get("source_hints") or []))
        return "\n".join(lines)
