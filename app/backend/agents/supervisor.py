# -*- coding: utf-8 -*-
"""Graph-style supervisor for the study-abroad AI agent.

The project is organized as a small multi-agent system:

1. profile_agent: user profile construction from questionnaire + chat memory
2. case_recommendation_agent: private cases Hybrid RAG
3. timeline_agent: task timeline + web research plan + case hints
4. essay_agent: files.json essay RAG + profile + cases
5. comparison_agent: multi-option comparison + web research plan + cases
6. material_agent: prepare.json material RAG + web research plan
7. visa_career_agent: visa and post-graduation planning + web research plan

The supervisor routes a user query to one or more specialist agents and returns
a compact, frontend-friendly result.  LLM calls can be added on top of each
agent result, but the graph is deterministic and testable without network.
"""

from __future__ import annotations

import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    from app.backend.agents.specialists import (
        CaseRecommendationAgent,
        ComparisonAgent,
        EssayAgent,
        MaterialAgent,
        ProfileAgent,
        TimelineAgent,
        VisaCareerAgent,
    )
    from app.backend.memory.memory_manager import MemoryManager
    from app.backend.rag.retriever import build_rag_context
    from app.backend.tools.llm_client import compact_profile, try_llm
except ImportError:  # Allows direct execution from app/backend/agents.
    import sys

    ROOT = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(ROOT))
    from app.backend.agents.specialists import (
        CaseRecommendationAgent,
        ComparisonAgent,
        EssayAgent,
        MaterialAgent,
        ProfileAgent,
        TimelineAgent,
        VisaCareerAgent,
    )
    from app.backend.memory.memory_manager import MemoryManager
    from app.backend.rag.retriever import build_rag_context
    from app.backend.tools.llm_client import compact_profile, try_llm


SYSTEM_INSTRUCTION = """你是轻留学 AI 留学中介/助手的 supervisor。
你需要根据用户问题路由到专业子 agent，并把结果整合成清晰、结构化、可执行的留学建议。
回答必须优先使用用户画像、企业私有案例库和私有文书/材料知识库。
涉及截止日期、签证政策、费用、项目要求等动态信息时，要提示以官方网页最新信息为准。
"""


INTENT_PATTERNS = {
    "profile": ["画像", "我的背景", "我叫", "记住", "偏好", "问卷", "背景是"],
    "case": ["案例", "路线", "推荐", "真实", "相似", "选校", "录取"],
    "timeline": ["时间线", "规划", "任务", "什么时候", "截止", "申请季", "todo", "计划"],
    "essay": ["文书", "sop", "ps", "个人陈述", "动机信", "essay", "statement"],
    "comparison": ["对比", "比较", "哪个更适合", "方案", "vs", "还是"],
    "materials": ["材料", "成绩单", "推荐信", "简历", "cv", "resume", "准备清单", "portfolio"],
    "visa": ["签证", "工签", "毕业后", "就业规划", "留下", "移民", "opt", "pgwp", "graduate visa"],
}


class StudyAbroadSupervisor:
    """Route user questions through the specialist-agent graph."""

    def __init__(self, memory_manager: MemoryManager | None = None):
        self.memory_manager = memory_manager or MemoryManager()
        self.profile_agent = ProfileAgent(self.memory_manager)
        self.agents = {
            "profile": self.profile_agent,
            "case": CaseRecommendationAgent(),
            "timeline": TimelineAgent(),
            "essay": EssayAgent(),
            "comparison": ComparisonAgent(),
            "materials": MaterialAgent(),
            "visa": VisaCareerAgent(),
        }

    def run(
        self,
        query: str,
        user_id: str = "visitor",
        conversation_id: str | None = None,
        questionnaire: dict[str, Any] | None = None,
        requested_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        conversation = self.memory_manager.get_conversation(user_id, conversation_id)
        conversation_id = conversation["conversation_id"]

        # Profile agent always gets the message first, because every turn may
        # contain user facts that improve long-term personalization.
        profile_result = self.profile_agent.run(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            questionnaire=questionnaire,
        )
        profile = profile_result["structured"]["profile"]

        explicit_route = requested_agents is not None
        route = requested_agents if explicit_route else self.route(query)
        route = [agent for agent in route if agent != "profile"]
        if not route and not explicit_route:
            route = ["case"]

        specialist_results = self._run_specialists_parallel(
            route=route,
            query=query,
            profile=profile,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        all_results = [profile_result] + specialist_results
        final_answer, answer_source = self._synthesize_answer(query, all_results, profile)
        self.memory_manager.append_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=final_answer,
            metadata={"agent": "supervisor", "route": route, "answer_source": answer_source},
        )

        return {
            "supervisor": "study_abroad_supervisor",
            "query": query,
            "conversation_id": conversation_id,
            "route": ["profile"] + route,
            "answer": final_answer,
            "answer_source": answer_source,
            "agent_results": all_results,
            "profile": profile,
            "confidence": self._aggregate_confidence(all_results),
        }

    def route(self, query: str) -> list[str]:
        lowered = query.lower()
        route = []
        for intent, patterns in INTENT_PATTERNS.items():
            if any(pattern.lower() in lowered for pattern in patterns):
                route.append(intent)

        if "case" not in route and any(token in lowered for token in ["推荐", "申请", "学校", "专业"]):
            route.append("case")
        if len(route) > 3 and "profile" in route:
            route.remove("profile")
        if not route:
            route = ["case"]

        # Multi-hop defaults for common broad requests.
        if "规划" in query and "timeline" not in route:
            route.append("timeline")
        if "材料" in query and "materials" not in route:
            route.append("materials")
        if "文书" in query and "essay" not in route:
            route.append("essay")

        return self._dedupe(route)

    def _run_specialists_parallel(
        self,
        route: list[str],
        query: str,
        profile: dict[str, Any],
        user_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        """Run independent specialist agents concurrently and preserve route order."""
        if not route:
            return []

        results_by_key: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(len(route), 4)) as executor:
            future_to_key = {}
            for agent_key in route:
                agent = self.agents.get(agent_key)
                if not agent:
                    continue
                future = executor.submit(
                    agent.run,
                    query=query,
                    profile=profile,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
                future_to_key[future] = agent_key

            for future in as_completed(future_to_key):
                agent_key = future_to_key[future]
                try:
                    results_by_key[agent_key] = future.result()
                except Exception as exc:  # Keep the supervisor resilient.
                    results_by_key[agent_key] = {
                        "agent": f"{agent_key}_agent",
                        "task": f"{agent_key} 模块",
                        "answer": f"这个模块暂时没有成功返回，原因：{exc}",
                        "structured": {"error": str(exc)},
                        "sources": [],
                        "confidence": 0.0,
                    }

        return [results_by_key[key] for key in route if key in results_by_key]

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def _synthesize_answer(self, query: str, results: list[dict[str, Any]], profile: dict[str, Any]) -> tuple[str, str]:
        fallback = self._deterministic_answer(results)
        llm_answer = self._llm_synthesize_answer(query=query, results=results, profile=profile, fallback=fallback)
        if llm_answer:
            return llm_answer, "llm"
        return fallback, "deterministic_fallback"

    def _deterministic_answer(self, results: list[dict[str, Any]]) -> str:
        lines = ["我按你的问题拆给对应的专业模块处理了。"]
        for result in results:
            if result["agent"] == "profile_agent":
                continue
            lines.append(f"\n【{result['task']}】")
            lines.append(result["answer"])
        profile_result = next((item for item in results if item["agent"] == "profile_agent"), None)
        if profile_result:
            missing = profile_result["structured"].get("missing_fields") or []
            if missing:
                lines.append(f"\n为了让后续推荐更准，建议补充：{', '.join(missing[:5])}。")
        lines.append("\n涉及官网截止日期、签证政策和费用的内容，我会把它标记为需要实时核对。")
        return "\n".join(lines)

    def _llm_synthesize_answer(
        self,
        query: str,
        results: list[dict[str, Any]],
        profile: dict[str, Any],
        fallback: str,
    ) -> str | None:
        module_summaries = []
        for result in results:
            if result.get("agent") == "profile_agent":
                continue
            structured = result.get("structured") or {}
            module_summaries.append(
                {
                    "task": result.get("task"),
                    "answer": result.get("answer"),
                    "structured": self._compact_json(structured),
                    "sources": (result.get("sources") or [])[:5],
                    "confidence": result.get("confidence"),
                }
            )

        profile_result = next((item for item in results if item.get("agent") == "profile_agent"), None)
        missing_fields = []
        if profile_result:
            missing_fields = (profile_result.get("structured") or {}).get("missing_fields") or []

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": "\n\n".join(
                    [
                        "请把下面的专业模块结果整合成一条自然、真实、有针对性的中文回答。",
                        "要求：直接回答用户，不要说“我按模块处理了”；不要编造未出现在模块结果里的录取、政策、截止日期或费用；信息不足时先给可执行假设，并提出最多 3 个追问；涉及动态政策和官网数据要提示实时核对。",
                        f"【用户问题】\n{query}",
                        f"【用户画像摘要】\n{compact_profile(profile)}",
                        "【模块结果】\n" + json.dumps(module_summaries, ensure_ascii=False, indent=2),
                        "【待补充字段】\n" + ("、".join(missing_fields[:6]) if missing_fields else "暂无"),
                        "【本地兜底草稿】\n" + fallback,
                    ]
                ),
            },
        ]
        return try_llm(messages, temperature=0.35)

    def _compact_json(self, value: Any, max_chars: int = 1800) -> Any:
        text = json.dumps(value, ensure_ascii=False)
        if len(text) <= max_chars:
            return value
        return text[: max_chars - 1].rstrip() + "..."

    def _aggregate_confidence(self, results: list[dict[str, Any]]) -> float:
        scores = [float(item.get("confidence", 0.0)) for item in results]
        return round(sum(scores) / max(len(scores), 1), 3)


def run_supervisor(
    query: str,
    user_id: str = "visitor",
    conversation_id: str | None = None,
    questionnaire: dict[str, Any] | None = None,
    requested_agents: list[str] | None = None,
    memory_manager: MemoryManager | None = None,
) -> dict[str, Any]:
    return StudyAbroadSupervisor(memory_manager=memory_manager).run(
        query=query,
        user_id=user_id,
        conversation_id=conversation_id,
        questionnaire=questionnaire,
        requested_agents=requested_agents,
    )


def build_agent_context(
    query: str,
    user_id: str = "visitor",
    conversation_id: str | None = None,
    entry: str = "chat",
    filters: dict[str, Any] | None = None,
    rag_k: int = 4,
    memory_manager: MemoryManager | None = None,
) -> dict[str, Any]:
    """Backward-compatible LLM prompt package for a single RAG answer."""
    manager = memory_manager or MemoryManager()
    conversation = manager.get_conversation(user_id, conversation_id)
    manager.append_message(
        user_id=user_id,
        conversation_id=conversation["conversation_id"],
        role="user",
        content=query,
        metadata={"entry": entry},
    )

    memory_context = manager.build_prompt_context(
        user_id=user_id,
        conversation_id=conversation["conversation_id"],
        current_query=query,
    )
    rag_context = build_rag_context(query, k=rag_k, filters=filters or {})
    user_prompt = "\n\n".join(
        [
            memory_context.prompt_context,
            "【真实案例召回】\n" + (rag_context["prompt_context"] or "暂无匹配案例"),
            "【用户最新问题】\n" + query,
        ]
    )

    return {
        "user_id": user_id,
        "conversation_id": conversation["conversation_id"],
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_prompt},
        ],
        "memory": memory_context,
        "rag": rag_context,
    }


def record_agent_answer(
    answer: str,
    user_id: str = "visitor",
    conversation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    memory_manager: MemoryManager | None = None,
) -> None:
    manager = memory_manager or MemoryManager()
    conversation = manager.get_conversation(user_id, conversation_id)
    manager.append_message(
        user_id=user_id,
        conversation_id=conversation["conversation_id"],
        role="assistant",
        content=answer,
        metadata=metadata or {},
    )


if __name__ == "__main__":
    demo = run_supervisor("GPA 3.55，有2年AI产品经验，想申请美国CS硕士，请给我推荐路线和时间线。")
    print(demo["answer"])
