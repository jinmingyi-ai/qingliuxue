# -*- coding: utf-8 -*-
"""Visa and post-graduation planning agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, goal_from_query, query_focus_line, web_source_from_result
from app.backend.tools.web_tools import web_research


class VisaCareerAgent:
    name = "visa_career_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = goal_from_query(query, profile)
        visa_web = web_research("visa", query, country=goal["country"], level=goal["level"], program=goal["major"])
        career_web = web_research("career", query, country=goal["country"], level=goal["level"], program=goal["major"])
        plan = self._build_plan(goal)
        answer = self._answer(query, goal, plan)
        return AgentResult(
            agent=self.name,
            task="签证和毕业后规划",
            answer=answer,
            structured={"goal": goal, "visa_and_career_plan": plan, "web_research": [visa_web, career_web]},
            sources=[
                web_source_from_result(visa_web, "visa"),
                web_source_from_result(career_web, "career"),
            ],
            confidence=0.74,
        ).to_dict()

    def _build_plan(self, goal: dict[str, Any]) -> dict[str, Any]:
        country = goal["country"]
        visa_type = {
            "US": "F-1 Student Visa",
            "UK": "Student visa",
            "Canada": "Study Permit",
            "Australia": "Student visa subclass 500",
        }.get(country, "Student visa / study permit")
        post_study = {
            "US": ["OPT", "STEM OPT（如专业符合）", "H-1B或其他长期身份需另行规划"],
            "UK": ["Graduate visa", "Skilled Worker route"],
            "Canada": ["PGWP", "Express Entry / PNP 需结合专业和工作经验"],
            "Australia": ["Temporary Graduate visa subclass 485", "技术移民/州担保需结合职业清单"],
        }.get(country, ["以目标国家移民局官网为准"])
        return {
            "visa_type": visa_type,
            "before_admission": [
                "提前准备护照、资金来源说明、成绩和在读/毕业证明。",
                "选校时同步确认项目是否符合毕业后工签或职业路径要求。",
            ],
            "after_offer": [
                "确认入读并获取学校签证文件或录取确认文件。",
                "准备资金证明、体检/保险、签证表格和面签/生物信息要求。",
            ],
            "post_graduation_options": post_study,
            "career_planning": [
                "第一学期开始建立简历、LinkedIn/作品集和校内career service联系。",
                "把课程项目转化成可展示成果，优先积累当地实习或研究/行业项目。",
                "毕业前6-9个月开始投递，确认工签申请窗口和雇主要求。",
            ],
            "policy_warning": "签证费用、材料和毕业后工签政策变化频繁，必须以政府官网最新页面为准。",
        }

    def _answer(self, query: str, goal: dict[str, Any], plan: dict[str, Any]) -> str:
        focus = query_focus_line(
            query,
            ["澳洲", "澳大利亚", "485", "专业", "签证", "资金", "就业", "工签", "PGWP", "OPT", "Graduate visa"],
            "我会把它放进签证和毕业后路径判断。",
        )
        lines = [
            f"如果你考虑 {goal['country_label']}，签证和毕业后路径要从选校阶段就一起看，别等拿到 offer 才补。"
        ]
        if focus:
            lines.append(focus)
        lines.extend(
            [
                f"签证主线: 按 {plan['visa_type']} 准备。",
                f"录取前: {'；'.join(plan['before_admission'])}",
                f"录取后: {'；'.join(plan['after_offer'])}",
                f"毕业后路径: {'；'.join(plan['post_graduation_options'])}",
                f"就业动作: {'；'.join(plan['career_planning'])}",
                f"提醒: {plan['policy_warning']}",
            ]
        )
        return "\n".join(lines)
