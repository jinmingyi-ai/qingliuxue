# -*- coding: utf-8 -*-
"""Multi-option comparison agent."""

from __future__ import annotations

import re
from typing import Any

from app.backend.agents.specialists.base import (
    AgentResult,
    COUNTRY_LABELS,
    goal_from_query,
    query_focus_line,
    source_from_rag_item,
    web_source_from_result,
)
from app.backend.rag.retriever import build_rag_context
from app.backend.tools.web_tools import web_research


class ComparisonAgent:
    name = "comparison_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = goal_from_query(query, profile)
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
        answer = self._answer(query, matrix, recommendation)
        sources = []
        for ctx in case_contexts:
            sources.extend(source_from_rag_item(item, "case_rag") for item in ctx.get("cases") or [])
        sources.extend(web_source_from_result(item, "comparison") for item in web_results)
        return AgentResult(
            agent=self.name,
            task="多方案对比",
            answer=answer,
            structured={"goal": goal, "options": options, "comparison_matrix": matrix, "recommendation": recommendation, "web_research": web_results},
            sources=sources,
            confidence=0.8,
        ).to_dict()

    def _infer_options(self, query: str, goal: dict[str, Any]) -> list[dict[str, Any]]:
        countries = self._countries_from_query(query)
        explicit_countries = bool(countries)
        if not countries:
            countries = [goal["country"]]
            if goal["country"] != "UK":
                countries.append("UK")
            if goal["country"] != "Canada":
                countries.append("Canada")
        countries = countries[:3]

        majors = self._majors_from_text(query)
        if not majors:
            majors = [goal["major"]]

        if not explicit_countries and len(majors) >= 2:
            return [self._option(goal["country"], major) for major in majors[:4]]

        options = []
        if len(countries) >= 2:
            segments = re.split(r"\s*(?:和|还是|vs|VS|/|、|，|,)\s*", query)
            for country in countries:
                segment = next((part for part in segments if country in self._countries_from_query(part)), query)
                segment_majors = self._majors_from_text(segment)
                options.append(self._option(country, (segment_majors or majors)[0]))
        else:
            for country in countries:
                for major in majors[:3]:
                    options.append(self._option(country, major))
        return options[:4]

    def _option(self, country: str, major: str) -> dict[str, Any]:
        return {
            "option_id": f"{country}_{major}".replace(" ", "_"),
            "country": country,
            "country_label": COUNTRY_LABELS.get(country, country),
            "major": major,
        }

    def _countries_from_query(self, query: str) -> list[str]:
        countries = []
        lowered = query.lower()
        if "英港新澳" in query:
            countries.extend(["UK", "Hong Kong", "Singapore", "Australia"])
        for country, label in COUNTRY_LABELS.items():
            aliases = {
                "US": ["美国", "美研", "us", "usa"],
                "UK": ["英国", "英研", "uk", "英"],
                "Canada": ["加拿大", "canada"],
                "Australia": ["澳洲", "澳大利亚", "australia", "澳"],
                "Singapore": ["新加坡", "singapore"],
                "Hong Kong": ["香港", "港校", "hong kong", "港"],
            }.get(country, [label, country])
            if any(alias.lower() in lowered for alias in aliases):
                countries.append(country)
        return list(dict.fromkeys(countries))

    def _majors_from_text(self, text: str) -> list[str]:
        majors = []
        if re.search(r"business analytics|商业分析|商分|\bba\b", text, re.I) or "BA" in text:
            majors.append("Business Analytics")
        if re.search(r"data science|\bds\b|数据科学|数据分析|analytics", text, re.I) or "DS" in text:
            majors.append("Data Science")
        if re.search(r"\bcs\b|计算机|computer|人工智能|\bai\b", text, re.I) or "CS" in text:
            majors.append("Computer Science")
        if re.search(r"\bit\b|信息技术", text, re.I) or "IT" in text:
            majors.append("Information Technology")
        if re.search(r"商科|business|金融|finance", text, re.I):
            majors.append("Business")
        return list(dict.fromkeys(majors))

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
            "US": ["项目选择多", "CS/AI就业资源强", "相似案例支持较多"],
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

    def _answer(self, query: str, matrix: list[dict[str, Any]], recommendation: dict[str, Any]) -> str:
        lines = [
            "这个问题不能只看排名，建议按匹配度、成本、就业和申请节奏一起比；这样更接近真实决策。"
        ]
        focus = query_focus_line(
            query,
            ["CS", "DS", "IS", "名校", "coop", "加拿大", "回国", "当地", "选校", "英", "港", "新", "澳"],
            "我会把这些作为方案排序的核心维度。",
        )
        if focus:
            lines.append(focus)
        for item in matrix:
            label = self._country_display(item["country"])
            lines.append(
                f"- {label} {item['major']}: 总分 {item['overall_score']}。优势: {'；'.join(item['advantages'][:2])}；风险: {'；'.join(item['risks'][:2])}；案例支撑 {item['case_support_count']} 条。"
            )
        primary = self._option_label(recommendation.get("primary_option") or "")
        lines.append(f"初步建议优先看 {primary}。{recommendation.get('next_step')}")
        lines.append("下一步把前2个方案各拆成5-8个具体项目，官网核对学费、课程、录取要求和就业数据后再做最终排序。")
        return "\n".join(lines)

    def _option_label(self, option_id: str) -> str:
        for country, label in COUNTRY_LABELS.items():
            if option_id.startswith(country):
                return option_id.replace(country, self._country_display(country)).replace("_", " ")
        return option_id.replace("_", " ")

    def _country_display(self, country: str) -> str:
        if country == "Australia":
            return "澳大利亚/澳洲"
        if country == "Hong Kong":
            return "中国香港/香港"
        return COUNTRY_LABELS.get(country, country)
