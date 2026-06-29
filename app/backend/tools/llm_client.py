# -*- coding: utf-8 -*-
"""Small LLM wrapper used by the chat supervisor.

Production chat must use a real model response.  This module therefore raises
explicit errors instead of silently returning deterministic fallback text.
"""

from __future__ import annotations

from typing import Any


class LLMCallError(RuntimeError):
    """Raised when the configured LLM cannot produce a real answer."""


def call_llm(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    try:
        from app.backend.utils.llm import get_llm
    except Exception as exc:
        raise LLMCallError(f"LLM 客户端初始化失败：{exc}") from exc

    try:
        llm = get_llm(temperature=temperature)
        response = llm.invoke(messages)
        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        fallback_text = str(response).strip() if response else ""
        if fallback_text:
            return fallback_text
    except Exception as exc:
        raise LLMCallError(f"LLM 调用失败：{exc}") from exc
    raise LLMCallError("LLM 返回了空内容")


def try_llm(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    return call_llm(messages, temperature=temperature)


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
