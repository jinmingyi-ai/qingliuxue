# -*- coding: utf-8 -*-
"""Small LLM wrapper with graceful fallback.

Agents should be able to run in local tests without network access.  When an
API key and dependencies are available, this wrapper can call the configured
xAI/OpenAI-compatible model.  Otherwise it returns None and agents use their
deterministic structured fallback.
"""

from __future__ import annotations

from typing import Any


def try_llm(messages: list[dict[str, str]], temperature: float = 0.2) -> str | None:
    try:
        from app.backend.utils.llm import get_llm

        llm = get_llm(temperature=temperature)
        response = llm.invoke(messages)
        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        return str(response).strip() if response else None
    except Exception:
        return None


def compact_profile(profile: dict[str, Any]) -> str:
    academic = profile.get("academic") or {}
    goals = profile.get("goals") or {}
    experiences = profile.get("experiences") or {}
    preferences = profile.get("preferences") or {}
    lines = []
    if profile.get("display_name"):
        lines.append(f"称呼={profile['display_name']}")
    if academic.get("major"):
        lines.append(f"背景专业={academic['major']}")
    if academic.get("gpa") is not None:
        lines.append(f"GPA={academic['gpa']}")
    if goals.get("target_level"):
        lines.append(f"目标阶段={goals['target_level']}")
    if goals.get("target_countries"):
        lines.append(f"目标国家={', '.join(goals['target_countries'])}")
    if goals.get("target_majors"):
        lines.append(f"目标专业={', '.join(goals['target_majors'])}")
    if goals.get("application_year"):
        lines.append(f"申请年份={goals['application_year']}")
    if experiences.get("work_years"):
        lines.append(f"工作/项目年限={experiences['work_years']}年")
    flags = [key for key, value in experiences.items() if isinstance(value, bool) and value]
    if flags:
        lines.append(f"经历标签={', '.join(flags)}")
    if preferences.get("priorities"):
        lines.append(f"偏好={', '.join(preferences['priorities'])}")
    return "；".join(lines) or "画像信息不足"
