# -*- coding: utf-8 -*-
"""Shared helpers for specialist study-abroad agents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


COUNTRY_LABELS = {
    "US": "美国",
    "UK": "英国",
    "Canada": "加拿大",
    "Australia": "澳大利亚",
    "Singapore": "新加坡",
    "Hong Kong": "中国香港",
}

LEVEL_LABELS = {
    "undergrad": "本科",
    "graduate": "硕士",
    "phd": "博士",
}


@dataclass
class AgentResult:
    agent: str
    task: str
    answer: str
    structured: dict[str, Any]
    sources: list[dict[str, Any]]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "task": self.task,
            "answer": self.answer,
            "structured": self.structured,
            "sources": self.sources,
            "confidence": self.confidence,
        }


def profile_goal(profile: dict[str, Any]) -> dict[str, Any]:
    goals = profile.get("goals") or {}
    academic = profile.get("academic") or {}
    experiences = profile.get("experiences") or {}
    country = (goals.get("target_countries") or ["US"])[0]
    level = goals.get("target_level") or "graduate"
    major = (goals.get("target_majors") or [academic.get("major") or "Computer Science"])[0]
    return {
        "country": country,
        "country_label": COUNTRY_LABELS.get(country, country),
        "level": level,
        "level_label": LEVEL_LABELS.get(level, level),
        "major": major,
        "gpa": academic.get("gpa"),
        "percentage_score": academic.get("percentage_score"),
        "score_scale": academic.get("score_scale"),
        "work_years": experiences.get("work_years"),
        "application_year": goals.get("application_year"),
        "preferences": (profile.get("preferences") or {}).get("priorities") or [],
        "budget": (profile.get("preferences") or {}).get("budget"),
    }


def goal_from_query(query: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Prefer explicit constraints in the current user question over memory."""
    goal = profile_goal(profile)
    country = infer_country_from_query(query, fallback=goal["country"])
    level = infer_level_from_query(query, fallback=goal["level"])
    major = infer_major_from_query(query, fallback=goal["major"])
    goal.update(
        {
            "country": country,
            "country_label": COUNTRY_LABELS.get(country, country),
            "level": level,
            "level_label": LEVEL_LABELS.get(level, level),
            "major": major,
        }
    )
    return goal


def infer_country_from_query(query: str, fallback: str = "US") -> str:
    lowered = query.lower()
    patterns = [
        ("US", ["美国", "美研", "美本", "us", "usa", "america"]),
        ("UK", ["英国", "英研", "英本", "uk"]),
        ("Canada", ["加拿大", "canada"]),
        ("Australia", ["澳洲", "澳大利亚", "australia"]),
        ("Singapore", ["新加坡", "singapore"]),
        ("Hong Kong", ["香港", "港校"]),
    ]
    for country, aliases in patterns:
        if any(alias in lowered for alias in aliases):
            return country
    return fallback


def infer_level_from_query(query: str, fallback: str = "graduate") -> str:
    lowered = query.lower()
    if any(token in lowered for token in ["博士", "phd"]):
        return "phd"
    if any(token in lowered for token in ["硕士", "硕申", "研究生", "master", "msc", "graduate"]):
        return "graduate"
    if any(token in lowered for token in ["本科申请", "申请本科", "读本科", "本科项目", "本申", "undergrad", "bachelor"]):
        return "undergrad"
    return fallback


def infer_major_from_query(query: str, fallback: str = "Computer Science") -> str:
    lowered = query.lower()
    patterns = [
        ("Business Analytics", [r"\bba\b", r"business analytics", r"商业分析", r"商分"]),
        ("Data Science", [r"data science", r"\bds\b", r"数据科学", r"数据分析", r"analytics"]),
        ("Computer Science", [r"\bcs\b", r"computer science", r"计算机", r"转码", r"软件", r"人工智能", r"\bai\b"]),
        ("Human-Computer Interaction", [r"\bhci\b", r"人机交互", r"用户研究", r"\bux\b"]),
        ("Information Systems", [r"information systems", r"\bis\b", r"信息系统"]),
        ("Information Technology", [r"\bit\b", r"信息技术"]),
        ("Robotics", [r"robotics", r"机器人"]),
        ("Finance", [r"finance", r"金融"]),
        ("Business", [r"business", r"商科", r"管理"]),
    ]
    for major, regexes in patterns:
        if any(re.search(pattern, lowered, re.I) for pattern in regexes):
            return major
    return fallback


def extract_json_safe_text(value: Any, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def source_from_rag_item(item: dict[str, Any], source_type: str) -> dict[str, Any]:
    meta = item.get("metadata") or {}
    return {
        "type": source_type,
        "id": meta.get("id") or meta.get("profile_id") or meta.get("case_key"),
        "country": meta.get("country"),
        "label": meta.get("label") or meta.get("level"),
        "score": item.get("score"),
        "reasons": item.get("reasons") or [],
    }


def web_source_from_result(web: dict[str, Any], topic: str) -> dict[str, Any]:
    return {
        "type": "web_search" if web.get("status") == "live_search" else "web_research_plan",
        "topic": topic,
        "status": web.get("status"),
        "provider": web.get("provider"),
        "source_hints": web.get("source_hints") or [],
        "results": [
            {"title": item.get("title"), "url": item.get("url"), "score": item.get("score")}
            for item in (web.get("results") or [])[:5]
        ],
        "error": web.get("error"),
    }


def query_focus_line(query: str, keywords: list[str], suffix: str = "我会把这些作为判断重点。") -> str:
    lowered = query.lower()
    hits = []
    for keyword in keywords:
        if keyword.lower() in lowered and keyword not in hits:
            hits.append(keyword)
    if not hits:
        return ""
    return "你提到的 " + "、".join(hits[:5]) + "，" + suffix
