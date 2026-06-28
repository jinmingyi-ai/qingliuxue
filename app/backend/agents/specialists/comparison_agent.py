# -*- coding: utf-8 -*-
"""Multi-option comparison agent."""

from __future__ import annotations

import re
from typing import Any

from app.backend.agents.specialists.base import AgentResult, COUNTRY_LABELS, profile_goal, source_from_rag_item
from app.backend.rag.retriever import build_rag_context
from app.backend.tools.web_tools import web_research


class ComparisonAgent:
    name = "comparison_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = profile_goal(profile)
        options = self._infer_options(query, goal)
        web_results = [
            web_research("comparison", query, country=option.get("country"), level=goal["level"], program=option.get("major"))
            for option in options
        ]
        case_contexts = [
            build_rag_context(
                f"{query} {option.get('country_label')} {goal['level_label']} {option.get('major')} 多方案对比",
                k=2,
                filters={"country": option.get("country"), "level": goal["level"], "major": option.get("major")},
            )
            for option in options
        ]
        matrix = self._comparison_matrix(options, goal, case_contexts)
        recommendation = self._recommend(matrix, goal)
        answer = self._answer(matrix, recommendation)
        sources = []
        for ctx in case_contexts:
            sources.extend(source_from_rag_item(item, "case_rag") for item in ctx.get("cases") or [])
        sources.extend({"type": "web_research_plan", "topic": "comparison", "source_hints": item["source_hints"]} for item in web_results)
        return AgentResult(
            agent=self.name,
            task="多方案对比",
            answer=answer,
            structured={"goal": goal, "options": options, "comparison_matrix": matrix, "recommendation": recommendation, "web_research": web_results},
            sources=sources,
            confidence=0.8,
        ).to_dict()

    def _infer_options(self, query: str, goal: dict[str, Any]) -> list[dict[str, Any]]:
        countries = []
        for country, label in COUNTRY_LABELS.items():
            if label in query or country.lower() in query.lower():
                countries.append(country)
        if not countries:
            countries = [goal["country"]]
            if goal["country"] != "UK":
                countries.append("UK")
            if goal["country"] != "Canada":
                countries.append("Canada")
        countries = countries[:3]

        majors = []
        if re.search(r"data|数据|商业分析|analytics", query, re.I):
            majors.append("Data Science")
        if re.search(r"cs|计算机|computer|ai|人工智能", query, re.I):
            majors.append("Computer Science")
        if re.search(r"商科|business|金融|finance", query, re.I):
            majors.append("Business")
        if not majors:
            majors = [goal["major"]]

        options = []
        for country in countries:
            for major in majors[:2]:
                options.append(
                    {
                        "option_id": f"{country}_{major}".replace(" ", "_"),
                        "country": country,
                        "country_label": COUNTRY_LABELS.get(country, country),
                        "major": major,
                    }
                )
        return options[:4]

    def _comparison_matrix(
        self,
        options: list[dict[str, Any]],
        goal: dict[str, Any],
        case_contexts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        matrix = []
        for option, cases in zip(options, case_contexts):
            country = option["country"]
            case_count = len(cases.get("cases") or [])
            cost_score = {"US": 2, "UK": 3, "Canada": 4, "Australia": 3}.get(country, 3)
            career_score = {"US": 5, "UK": 3, "Canada": 4, "Australia": 4}.get(country, 3)
            speed_score = {"UK": 5, "Australia": 4, "US": 3, "Canada": 3}.get(country, 3)
            fit_score = min(5, 3 + case_count)
            total = round((cost_score + career_score + speed_score + fit_score) / 4, 2)
            matrix.append(
                {
                    "option_id": option["option_id"],
                    "country": country,
                    "major": option["major"],
                    "fit_score": fit_score,
                    "cost_score": cost_score,
                    "career_score": career_score,
                    "speed_score": speed_score,
                    "overall_score": total,
                    "advantages": self._advantages(country),
                    "risks": self._risks(country, goal),
                    "case_support_count": case_count,
                }
            )
        matrix.sort(key=lambda item: item["overall_score"], reverse=True)
        return matrix

    def _advantages(self, country: str) -> list[str]:
        return {
            "US": ["项目选择多", "CS/AI就业资源强", "真实案例库支持较多"],
            "UK": ["学制短", "申请路径清晰", "适合快速拿学位"],
            "Canada": ["移民和毕业后工作路径相对友好", "成本通常低于美国"],
            "Australia": ["申请节奏灵活", "毕业后工作签证路径明确"],
        }.get(country, ["需要结合具体项目判断"])

    def _risks(self, country: str, goal: dict[str, Any]) -> list[str]:
        risks = {
            "US": ["成本高", "签证和就业不确定性需要提前规划"],
            "UK": ["一年制节奏紧", "转专业或就业需要更强主动性"],
            "Canada": ["研究型项目匹配导师很关键", "部分项目名额少"],
            "Australia": ["院校差异明显", "需要核对职业认证或签证细节"],
        }.get(country, ["信息不足，需要查官网"])
        if "budget_sensitive" in goal.get("preferences", []):
            risks.append("用户预算敏感，需要把学费和生活费作为硬指标。")
        return risks

    def _recommend(self, matrix: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any]:
        best = matrix[0] if matrix else {}
        return {
            "primary_option": best.get("option_id"),
            "reason": "综合案例支持、就业、成本和申请节奏后排序最高。",
            "next_step": "把排名前2的方案拆成具体学校/项目清单，并核对官网最新要求。",
        }

    def _answer(self, matrix: list[dict[str, Any]], recommendation: dict[str, Any]) -> str:
        lines = ["我先按匹配度、成本、就业、申请节奏四个维度做对比："]
        for item in matrix:
            lines.append(
                f"- {item['country']} {item['major']}: 总分 {item['overall_score']}，优势: {'；'.join(item['advantages'][:2])}，风险: {'；'.join(item['risks'][:2])}"
            )
        lines.append(f"初步建议优先看 {recommendation.get('primary_option')}。{recommendation.get('next_step')}")
        return "\n".join(lines)
