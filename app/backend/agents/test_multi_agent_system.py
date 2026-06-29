# -*- coding: utf-8 -*-
"""End-to-end smoke tests for the multi-agent study-abroad system."""

from __future__ import annotations

import tempfile
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ALLOW_DETERMINISTIC_CHAT_FALLBACK", "1")

from app.backend.agents.specialists import (
    CaseRecommendationAgent,
    ComparisonAgent,
    EssayAgent,
    MaterialAgent,
    ProfileAgent,
    TimelineAgent,
    VisaCareerAgent,
)
from app.backend.agents.supervisor import StudyAbroadSupervisor
from app.backend.memory.memory_manager import MemoryManager
from app.backend.rag.knowledge_base import build_all_knowledge_indexes, build_knowledge_context


def sample_profile() -> dict:
    return {
        "display_name": "小林",
        "academic": {
            "current_level": "undergrad",
            "school": "双非一本",
            "major": "Computer Science",
            "gpa": 3.55,
            "language_scores": {"ielts": 7.0},
        },
        "goals": {
            "target_level": "graduate",
            "target_countries": ["US"],
            "target_majors": ["Computer Science"],
            "application_year": 2027,
        },
        "experiences": {
            "work_years": 2.0,
            "has_research": False,
            "has_internship": True,
            "has_work": True,
            "has_competition": False,
            "has_project": True,
            "has_product": True,
            "has_ai": True,
        },
        "preferences": {"priorities": ["career_outcome", "budget_sensitive"]},
        "constraints": [],
        "notes": [],
    }


def assert_check(name: str, condition: bool) -> bool:
    print(f"{name}: {'PASS' if condition else 'FAIL'}")
    return condition


def test_knowledge_retrieval() -> bool:
    build_all_knowledge_indexes()
    essay = build_knowledge_context(
        "essay",
        "美国CS硕士SOP怎么写，突出AI产品经历",
        k=2,
        filters={"country": "US", "level": "graduate", "document_type": "Statement of Purpose"},
    )
    material = build_knowledge_context(
        "prepare",
        "美国研究生申请材料清单 推荐信 成绩单",
        k=1,
        filters={"country": "US", "level": "graduate"},
    )
    return all(
        [
            assert_check("essay_rag_top_us", essay["results"][0]["metadata"]["country"] == "US"),
            assert_check("essay_rag_has_sop", "Statement" in " ".join(essay["results"][0]["metadata"]["document_types"])),
            assert_check("prepare_rag_top_us", material["results"][0]["metadata"]["id"] == "material_prep_us_001"),
        ]
    )


def test_specialist_agents() -> bool:
    profile = sample_profile()
    checks = []
    agents = [
        ("case_agent", CaseRecommendationAgent(), "给我推荐美国CS硕士真实案例路线", "recommended_routes"),
        ("timeline_agent", TimelineAgent(), "给我申请时间线和任务规划", "timeline"),
        ("essay_agent", EssayAgent(), "SOP文书怎么写", "essay_strategy"),
        ("comparison_agent", ComparisonAgent(), "美国和英国CS硕士方案对比", "comparison_matrix"),
        ("material_agent", MaterialAgent(), "申请材料准备清单", "material_checklist"),
        ("visa_agent", VisaCareerAgent(), "签证和毕业后工作规划", "visa_and_career_plan"),
    ]
    for name, agent, query, expected_key in agents:
        result = agent.run(query, profile=profile)
        checks.append(assert_check(f"{name}_agent_name", result["agent"].endswith("_agent")))
        checks.append(assert_check(f"{name}_has_answer", bool(result["answer"])))
        checks.append(assert_check(f"{name}_structured_key", expected_key in result["structured"]))
        checks.append(assert_check(f"{name}_confidence", result["confidence"] >= 0.5))
    return all(checks)


def test_profile_and_supervisor() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manager = MemoryManager(store_path=Path(tmp) / "memory.json")
        profile_agent = ProfileAgent(manager)
        profile_result = profile_agent.run(
            "我叫小林，GPA 3.55，有2年AI产品工作经验，想申请美国CS硕士，重视就业和性价比。",
            user_id="visitor",
        )
        profile = profile_result["structured"]["profile"]
        supervisor = StudyAbroadSupervisor(memory_manager=manager)
        result = supervisor.run(
            "帮我做一个路线推荐、时间线、SOP文书策略和材料准备清单。",
            user_id="visitor",
        )
        checks = [
            assert_check("profile_name", profile["display_name"] == "小林"),
            assert_check("profile_gpa", profile["academic"]["gpa"] == 3.55),
            assert_check("profile_country", "US" in profile["goals"]["target_countries"]),
            assert_check("profile_work", profile["experiences"]["work_years"] == 2.0),
            assert_check("supervisor_route_case", "case" in result["route"]),
            assert_check("supervisor_route_timeline", "timeline" in result["route"]),
            assert_check("supervisor_route_essay", "essay" in result["route"]),
            assert_check("supervisor_route_materials", "materials" in result["route"]),
            assert_check("supervisor_answer", "基于真实案例推荐" in result["answer"] and "文书策略" in result["answer"]),
            assert_check("supervisor_confidence", result["confidence"] >= 0.7),
        ]
        return all(checks)


def run_tests() -> bool:
    print("\n=== Knowledge Retrieval ===")
    ok_knowledge = test_knowledge_retrieval()
    print("\n=== Specialist Agents ===")
    ok_agents = test_specialist_agents()
    print("\n=== Profile + Supervisor ===")
    ok_supervisor = test_profile_and_supervisor()
    all_ok = ok_knowledge and ok_agents and ok_supervisor
    print("\nALL PASSED" if all_ok else "\nSOME TESTS FAILED")
    return all_ok


if __name__ == "__main__":
    raise SystemExit(0 if run_tests() else 1)
