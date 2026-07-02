# -*- coding: utf-8 -*-
"""Essay strategy and guidance agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, goal_from_query, query_focus_line, source_from_rag_item
from app.backend.rag.knowledge_base import build_knowledge_context
from app.backend.rag.retriever import build_rag_context


class EssayAgent:
    name = "essay_agent"

    def run(self, query: str, profile: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        profile = profile or {}
        goal = goal_from_query(query, profile)
        document_type = self._document_type(goal["country"], query)
        knowledge = build_knowledge_context(
            "essay",
            f"{query} {goal['country_label']} {goal['level_label']} {document_type} 文书策略 常见错误 结构",
            k=4,
            filters={"country": goal["country"], "level": goal["level"], "document_type": document_type},
        )
        cases = build_rag_context(
            f"{query} {goal['country_label']} {goal['major']} 文书 申请策略 背景提升",
            k=2,
            filters={"country": goal["country"], "level": goal["level"], "major": goal["major"]},
        )
        strategy = self._build_strategy(goal, document_type, knowledge["results"], cases["cases"])
        answer = self._answer(query, goal, document_type, strategy)
        sources = [source_from_rag_item(item, "essay_knowledge") for item in knowledge["results"]]
        sources.extend(source_from_rag_item(item, "case_rag") for item in cases["cases"])
        return AgentResult(
            agent=self.name,
            task="文书策略和指导",
            answer=answer,
            structured={
                "goal": goal,
                "document_type": document_type,
                "essay_strategy": strategy,
                "knowledge_count": len(knowledge["results"]),
                "case_count": len(cases["cases"]),
            },
            sources=sources,
            confidence=0.88 if knowledge["results"] else 0.5,
        ).to_dict()

    def _document_type(self, country: str, query: str) -> str:
        lowered = query.lower()
        if "ps" in lowered or "个人陈述" in lowered:
            return "Personal Statement"
        if "sop" in lowered or "动机" in lowered:
            return "Statement of Purpose"
        if country == "US":
            return "Statement of Purpose"
        if country == "UK":
            return "Personal Statement"
        return "Personal Statement"

    def _build_strategy(
        self,
        goal: dict[str, Any],
        document_type: str,
        knowledge_items: list[dict[str, Any]],
        cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        experiences = []
        if goal.get("work_years"):
            experiences.append(f"{goal['work_years']}年工作/项目经历")
        if "career_outcome" in goal.get("preferences", []):
            experiences.append("就业导向")

        case_strategies = []
        for item in cases:
            raw = item.get("raw_profile") or {}
            case_strategies.extend(raw.get("key_strategies") or [])

        retrieved_focus = []
        common_mistakes = []
        for item in knowledge_items:
            raw = item.get("raw") or {}
            retrieved_focus.extend(raw.get("core_focus") or [])
            common_mistakes.extend(raw.get("common_mistakes") or [])
            common_mistakes.extend(raw.get("china_student_pain_points") or [])

        main_thesis = (
            f"围绕“{goal['major']}能力如何从经历中形成，并为什么适合{goal['country_label']}项目”建立主线。"
        )
        if goal.get("work_years"):
            main_thesis = f"把{goal['work_years']}年真实项目/工作经历写成能力成长主线，而不是简单罗列岗位。"

        return {
            "main_thesis": main_thesis,
            "recommended_structure": [
                "开头: 用一个具体问题/项目场景引出申请动机",
                "主体1: 学术或项目能力证据，强调方法、结果和反思",
                "主体2: 与目标项目课程、教授、资源的匹配",
                "主体3: 短期学习目标和长期职业目标",
                "结尾: 回到个人成长和项目契合度",
            ],
            "materials_to_collect": [
                "2-3个最能体现能力的项目/科研/实习故事",
                "量化成果、用户规模、模型指标、业务结果或竞赛结果",
                "目标项目的课程、实验室、教授、career resource",
            ],
            "case_strategies_to_borrow": case_strategies[:5],
            "retrieved_focus": retrieved_focus[:6],
            "common_mistakes_to_avoid": common_mistakes[:6],
            "tone": "具体、克制、有证据，不写空泛热爱和模板化夸学校。",
            "profile_signals_used": experiences,
        }

    def _answer(self, query: str, goal: dict[str, Any], document_type: str, strategy: dict[str, Any]) -> str:
        lines = [
            f"这类 {goal['country_label']} {goal['level_label']} {document_type} 最怕写成经历堆砌；你的重点应该是把经历写成一条能证明申请动机和能力成长的主线。",
            f"建议主线：{strategy['main_thesis']}",
            "推荐结构：",
        ]
        focus = query_focus_line(
            query,
            ["转专业", "数据科学", "个人陈述", "推荐信", "SOP", "配合", "BA", "定量", "证明", "文书", "素材", "清单"],
            "我会把它作为文书主线和素材筛选的重点。",
        )
        if focus:
            lines.insert(1, focus)
        if any(token in query for token in ["低GPA", "低 GPA", "绩点", "GPA", "成绩一般"]):
            lines.insert(
                1,
                "关于低GPA/绩点一般：文书里可以解释，但不要大段辩解。更好的写法是用1-2句说明客观原因或上升趋势，然后立刻用项目、科研、实习或后续高分课程证明你已经补上能力缺口。",
            )
        lines.extend(f"- {item}" for item in strategy["recommended_structure"])
        if strategy["materials_to_collect"]:
            lines.append("现在先收集素材：" + "；".join(strategy["materials_to_collect"][:3]))
        if "清单" in query:
            lines.append("文书素材清单建议按四类建表：学术课程/项目、实习或工作成果、转折与困难、目标项目匹配证据。")
        if "推荐信" in query:
            lines.append("推荐信和 SOP 的配合方式：SOP 讲你的动机和选择逻辑，推荐信用第三方细节证明你的能力，不要逐段重复同一件事。")
        if "定量" in query or "BA" in query:
            lines.append("BA/商科转向要证明定量能力：用统计、编程、建模、数据分析项目和量化结果替代空泛的“我数学不错”。")
        if strategy["case_strategies_to_borrow"]:
            lines.append("可借鉴的真实案例写法：" + "；".join(strategy["case_strategies_to_borrow"][:2]))
        if strategy["common_mistakes_to_avoid"]:
            lines.append("需要避免：" + "；".join(strategy["common_mistakes_to_avoid"][:3]))
        return "\n".join(lines)
