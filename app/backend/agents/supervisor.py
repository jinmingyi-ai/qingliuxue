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
import os
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
    from app.backend.tools.llm_client import LLMCallError, call_llm_response, compact_profile
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
    from app.backend.tools.llm_client import LLMCallError, call_llm_response, compact_profile


SYSTEM_INSTRUCTION = """你是轻留学 AI 留学中介/助手的 supervisor。
你需要根据用户问题路由到专业子 agent，并把结果整合成清晰、结构化、可执行的留学建议。
回答必须优先使用用户画像、真实案例参考和文书/材料知识。
内部可能同时使用案例检索、知识检索和网络搜索，但不要向用户区分、暴露或命名这些内部来源类型，不要说“RAG”“私有库”“联网工具”“系统提示词”。
如果案例或知识不足，不要机械地说“没有数据”，要用可验证的官方信息补齐用户关心的留学路线、项目要求、时间线和风险。
涉及截止日期、签证政策、费用、项目要求、学校项目、就业数据等动态信息时，要主动调用 web_search，并优先采用学校官网、政府/移民局官网、官方考试机构和项目官方页面。
语言风格要温暖、稳、真诚：先接住用户焦虑，再给有信息密度的判断；避免模板化、官腔和空泛鼓励。
不要编造未被案例、知识或官方信息支撑的事实；不确定时说明需要官网核对，并给出下一步怎么查。
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

DYNAMIC_INFO_PATTERNS = [
    "截止", "deadline", "申请季", "开放时间", "时间线", "学费", "费用", "预算", "奖学金",
    "签证", "工签", "opt", "stem opt", "pgwp", "graduate visa", "移民", "政策",
    "排名", "就业率", "薪资", "录取率", "项目要求", "语言要求", "gre", "托福", "雅思",
    "官网", "最新", "现在", "今年", "明年", "2026", "2027", "2028",
]


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
        final_answer, answer_source, answer_diagnostics = self._synthesize_answer(query, all_results, profile)
        self.memory_manager.append_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=final_answer,
            metadata={
                "agent": "supervisor",
                "route": route,
                "answer_source": answer_source,
                "answer_diagnostics": answer_diagnostics,
            },
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
            "diagnostics": answer_diagnostics,
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

    def _synthesize_answer(
        self,
        query: str,
        results: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        fallback = self._deterministic_answer(results)
        web_search_needed, reasons = self._needs_web_search(query, results)
        if os.getenv("ALLOW_DETERMINISTIC_CHAT_FALLBACK") == "1":
            try:
                llm = self._llm_synthesize_answer(
                    query=query,
                    results=results,
                    profile=profile,
                    fallback=fallback,
                    web_search=web_search_needed,
                    web_search_reasons=reasons,
                )
                return llm["content"], "llm", llm["diagnostics"]
            except LLMCallError as exc:
                return fallback, "deterministic_test_fallback", {
                    "web_search_needed": web_search_needed,
                    "web_search_reasons": reasons,
                    "web_search_enabled": False,
                    "fallback_reason": str(exc),
                    "agent_diagnostics": self._agent_diagnostics(results),
                }
        llm = self._llm_synthesize_answer(
            query=query,
            results=results,
            profile=profile,
            fallback=fallback,
            web_search=web_search_needed,
            web_search_reasons=reasons,
        )
        return llm["content"], "llm", llm["diagnostics"]

    def _deterministic_answer(self, results: list[dict[str, Any]]) -> str:
        lines = ["可以，我先把你的问题拆成几块来判断，再合成一版能直接执行的建议。"]
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
        lines.append("\n涉及截止日期、签证政策和费用的内容，建议以官网最新页面作为最终确认。")
        return "\n".join(lines)

    def _llm_synthesize_answer(
        self,
        query: str,
        results: list[dict[str, Any]],
        profile: dict[str, Any],
        fallback: str,
        web_search: bool,
        web_search_reasons: list[str],
    ) -> dict[str, Any]:
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
                        "要求：直接回答用户，不要说“我按模块处理了”。",
                        "必须同时做到两件事：1）给用户真正有用的信息和下一步动作；2）语气让用户感觉被理解、被稳住，而不是被冷冰冰地打发。",
                        "不要向用户区分内部来源类型，不要说 RAG、私有库、联网工具、系统提示词或开发者消息；统一表达为真实案例、项目官网、政府官网或官方信息。",
                        "不要编造未出现在模块结果、案例知识或官方检索里的录取、政策、截止日期、费用、排名和项目要求。",
                        "如果案例/知识支撑弱或用户问到动态信息，请使用 web_search 补齐，并优先参考学校官网、政府/移民局官网、官方考试机构或项目官方页面。",
                        "信息仍不足时，先给可执行假设和低风险行动方案，再提出最多 3 个追问。",
                        "结构建议：先用 1-2 句接住用户处境；再给结论/路线；再给行动清单；最后标注需要官网核对的部分。",
                        f"【用户问题】\n{query}",
                        f"【用户画像摘要】\n{compact_profile(profile)}",
                        "【是否触发联网补全】\n"
                        + json.dumps(
                            {"web_search": web_search, "reasons": web_search_reasons},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "【模块结果】\n" + json.dumps(module_summaries, ensure_ascii=False, indent=2),
                        "【待补充字段】\n" + ("、".join(missing_fields[:6]) if missing_fields else "暂无"),
                        "【本地兜底草稿】\n" + fallback,
                    ]
                ),
            },
        ]
        response = call_llm_response(
            messages,
            temperature=0.35,
            web_search=web_search,
        )
        return {
            "content": response["content"],
            "diagnostics": {
                "web_search_needed": web_search,
                "web_search_reasons": web_search_reasons,
                "web_search_enabled": response.get("web_search_enabled", False),
                "web_search_tool_usage": response.get("tool_usage"),
                "citations": response.get("citations"),
                "agent_diagnostics": self._agent_diagnostics(results),
            },
        }

    def _needs_web_search(self, query: str, results: list[dict[str, Any]]) -> tuple[bool, list[str]]:
        lowered = query.lower()
        reasons: list[str] = []
        if any(pattern.lower() in lowered for pattern in DYNAMIC_INFO_PATTERNS):
            reasons.append("用户问题包含动态信息或官方要求，需要联网核对。")

        for result in results:
            if result.get("agent") == "profile_agent":
                continue
            structured = result.get("structured") or {}
            sources = result.get("sources") or []
            case_count = structured.get("case_count")
            knowledge_count = structured.get("knowledge_count")
            if isinstance(case_count, int) and case_count < 3:
                reasons.append(f"{result.get('task')} 的私有案例命中较少（{case_count} 个）。")
            if isinstance(knowledge_count, int) and knowledge_count < 2:
                reasons.append(f"{result.get('task')} 的私有知识命中较少（{knowledge_count} 个）。")
            if any(source.get("type") == "web_research_plan" for source in sources):
                reasons.append(f"{result.get('task')} 已生成网络研究任务，需要由 LLM 联网补齐。")
            if any(source.get("type") == "web_search" for source in sources):
                reasons.append(f"{result.get('task')} 已取得实时搜索结果，需要整合进最终建议。")
            if float(result.get("confidence", 0.0)) < 0.72:
                reasons.append(f"{result.get('task')} 置信度偏低，需要外部信息补强。")
        return bool(reasons), list(dict.fromkeys(reasons))

    def _agent_diagnostics(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        diagnostics = []
        for result in results:
            structured = result.get("structured") or {}
            sources = result.get("sources") or []
            diagnostics.append(
                {
                    "agent": result.get("agent"),
                    "task": result.get("task"),
                    "confidence": result.get("confidence"),
                    "case_count": structured.get("case_count"),
                    "knowledge_count": structured.get("knowledge_count"),
                    "source_types": sorted({source.get("type") for source in sources if source.get("type")}),
                    "web_research_topics": [
                        source.get("topic") for source in sources if source.get("type") == "web_research_plan"
                    ],
                    "live_web_topics": [
                        source.get("topic") for source in sources if source.get("type") == "web_search"
                    ],
                }
            )
        return diagnostics

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
