# -*- coding: utf-8 -*-
"""Timeline and task planning agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.backend.agents.specialists.base import AgentResult, profile_goal, source_from_rag_item
from app.backend.rag.retriever import build_rag_context
from app.backend.tools.web_tools import web_research


class TimelineAgent:
    name = "timeline_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = profile_goal(profile)
        web = web_research("timeline", query, country=goal["country"], level=goal["level"], program=goal["major"])
        rag = build_rag_context(
            f"{query} {goal['country_label']} {goal['level_label']} {goal['major']} 时间线 任务规划",
            k=3,
            filters={"country": goal["country"], "level": goal["level"], "major": goal["major"]},
        )
        plan = self._build_plan(goal, rag.get("cases") or [])
        answer = self._answer(goal, plan)
        sources = [source_from_rag_item(item, "case_rag") for item in rag.get("cases") or []]
        sources.append({"type": "web_research_plan", "topic": "timeline", "source_hints": web["source_hints"]})
        return AgentResult(
            agent=self.name,
            task="时间线和任务规划",
            answer=answer,
            structured={"goal": goal, "timeline": plan, "web_research": web},
            sources=sources,
            confidence=0.82,
        ).to_dict()

    def _build_plan(self, goal: dict[str, Any], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        application_year = goal.get("application_year") or date.today().year + 1
        country = goal["country"]
        level = goal["level"]
        if country == "UK" and level == "undergrad":
            windows = [
                ("T-15到T-12个月", "UCAS选课与竞赛/活动主线整理"),
                ("T-11到T-9个月", "PS初稿、推荐人确认、语言考试"),
                ("T-8到T-6个月", "UCAS提交、牛剑/医学等提前批准备"),
                ("T-5到T-2个月", "面试/笔试、补交成绩、等待结果"),
                ("录取后", "确认offer、签证、住宿、行前准备"),
            ]
        elif country == "US" and level == "undergrad":
            windows = [
                ("高二下-暑假", "选校分层、活动主线、SAT/ACT/托福规划"),
                ("高三上 8-10月", "Common App主文书、推荐信、早申材料"),
                ("高三上 11-1月", "常规申请提交、补充文书"),
                ("高三下 2-4月", "面试、补材料、比较offer"),
                ("5月后", "确认入读、I-20、签证和住宿"),
            ]
        else:
            windows = [
                ("T-12到T-9个月", "确定国家/专业/项目梯度，补齐语言或标化"),
                ("T-9到T-6个月", "确定推荐人，准备简历、文书素材和成绩单"),
                ("T-6到T-3个月", "提交主轮申请，跟进推荐信和送分"),
                ("T-3到T月", "面试/补材料/奖学金申请，持续比较offer"),
                ("录取后", "押金、签证、住宿、体检/保险、行前规划"),
            ]

        case_lessons = []
        for item in cases[:2]:
            raw = item.get("raw_profile") or {}
            case_lessons.extend(raw.get("lessons") or [])

        plan = []
        for order, (window, focus) in enumerate(windows, 1):
            tasks = [focus]
            if order == 1:
                tasks.append("把申请目标拆成冲刺/匹配/保底三档。")
            if order == 2:
                tasks.append("把真实案例中的成功策略转化成个人材料主线。")
            if order == 3:
                tasks.append("逐项核对项目官网截止日期，避免错过奖学金/推荐信截止。")
            if case_lessons and order in {1, 2}:
                tasks.append(f"案例提醒: {case_lessons[0]}")
            plan.append(
                {
                    "order": order,
                    "window": window,
                    "target_year": application_year,
                    "focus": focus,
                    "tasks": tasks,
                    "deliverables": self._deliverables_for_order(order),
                    "risk_checks": self._risk_checks(goal, order),
                }
            )
        return plan

    def _deliverables_for_order(self, order: int) -> list[str]:
        deliverables = {
            1: ["目标项目长名单", "考试计划", "背景差距清单"],
            2: ["简历初稿", "文书素材库", "推荐人沟通邮件"],
            3: ["项目短名单", "网申账号", "主文书/补充文书定稿"],
            4: ["面试准备清单", "补材料追踪表", "offer对比表"],
            5: ["签证材料包", "住宿/押金安排", "行前任务表"],
        }
        return deliverables.get(order, [])

    def _risk_checks(self, goal: dict[str, Any], order: int) -> list[str]:
        checks = []
        if order <= 2 and not goal.get("gpa"):
            checks.append("GPA/均分未明确，选校梯度需要先估算。")
        if order <= 3:
            checks.append("截止日期和语言要求必须以项目官网最新页面为准。")
        if "budget_sensitive" in goal.get("preferences", []):
            checks.append("每轮选校都要同步记录学费、生活费和奖学金可能性。")
        return checks

    def _answer(self, goal: dict[str, Any], plan: list[dict[str, Any]]) -> str:
        lines = [f"这是按 {goal['country_label']} {goal['level_label']} {goal['major']} 方向生成的任务时间线："]
        for item in plan[:5]:
            lines.append(f"{item['window']}: {item['focus']}；交付物: {', '.join(item['deliverables'])}")
        return "\n".join(lines)
