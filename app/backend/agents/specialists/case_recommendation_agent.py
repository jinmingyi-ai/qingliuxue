# -*- coding: utf-8 -*-
"""Real-case route recommendation agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, profile_goal, source_from_rag_item
from app.backend.rag.retriever import build_rag_context


class CaseRecommendationAgent:
    name = "case_recommendation_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, k: int = 5, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = profile_goal(profile)
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
        answer = self._answer(recommendations, goal)

        return AgentResult(
            agent=self.name,
            task="基于真实案例推荐",
            answer=answer,
            structured={
                "goal": goal,
                "recommended_routes": recommendations,
                "rag_query": rag_query,
                "case_count": len(cases),
            },
            sources=[source_from_rag_item(item, "case_rag") for item in cases],
            confidence=0.9 if cases else 0.45,
        ).to_dict()

    def _compose_query(self, query: str, goal: dict[str, Any]) -> str:
        parts = [
            query,
            f"{goal['country_label']} {goal['level_label']} {goal['major']}",
        ]
        if goal.get("gpa"):
            parts.append(f"GPA {goal['gpa']}")
        if goal.get("work_years"):
            parts.append(f"{goal['work_years']}年工作经验")
        if goal.get("preferences"):
            parts.append("偏好 " + " ".join(goal["preferences"]))
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
                    "why_similar": ["当前案例库没有足够强匹配，需要放宽条件或补充用户信息。"],
                    "strategies_to_borrow": ["先明确国家、阶段、专业、GPA、语言和经历。"],
                    "lessons": [],
                }
            )
        return recommendations

    def _answer(self, recommendations: list[dict[str, Any]], goal: dict[str, Any]) -> str:
        top = recommendations[:3]
        lines = [
            f"我按 {goal['country_label']} {goal['level_label']} {goal['major']} 的方向，从真实案例库里选了最接近的路线。"
        ]
        for item in top:
            school = item.get("final_choice") or "待定项目"
            strategies = "；".join(item.get("strategies_to_borrow") or []) or "参考其申请主线和材料组织方式"
            lines.append(f"{item['tier']}: 参考 {item.get('student') or '相似同学'} -> {school}。可借鉴: {strategies}")
        return "\n".join(lines)
