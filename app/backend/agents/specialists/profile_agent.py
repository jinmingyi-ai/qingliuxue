# -*- coding: utf-8 -*-
"""User profile construction agent."""

from __future__ import annotations

from typing import Any

from app.backend.agents.specialists.base import AgentResult, extract_json_safe_text
from app.backend.memory.memory_manager import MemoryManager


class ProfileAgent:
    name = "profile_agent"

    def __init__(self, memory_manager: MemoryManager | None = None):
        self.memory_manager = memory_manager or MemoryManager()

    def run(
        self,
        query: str,
        user_id: str = "visitor",
        conversation_id: str | None = None,
        questionnaire: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        conversation = self.memory_manager.get_conversation(user_id, conversation_id)
        if query.strip():
            self.memory_manager.append_message(
                user_id=user_id,
                conversation_id=conversation["conversation_id"],
                role="user",
                content=query,
                metadata={"agent": self.name},
            )

        if questionnaire:
            self._ingest_questionnaire(user_id, conversation["conversation_id"], questionnaire)

        profile = self.memory_manager.export_user_profile(user_id)
        context = self.memory_manager.build_prompt_context(user_id, conversation["conversation_id"], current_query=query)
        missing = self._missing_fields(profile)
        answer = self._answer(profile, missing)

        return AgentResult(
            agent=self.name,
            task="用户画像构建",
            answer=answer,
            structured={
                "profile": profile,
                "missing_fields": missing,
                "memory_prompt_context": context.prompt_context,
                "conversation_id": conversation["conversation_id"],
            },
            sources=[{"type": "memory", "id": user_id, "conversation_id": conversation["conversation_id"]}],
            confidence=0.86 if len(missing) <= 4 else 0.68,
        ).to_dict()

    def _ingest_questionnaire(self, user_id: str, conversation_id: str, questionnaire: dict[str, Any]) -> None:
        questionnaire_text = self._questionnaire_to_text(questionnaire)
        if questionnaire_text:
            self.memory_manager.append_message(
                user_id=user_id,
                conversation_id=conversation_id,
                role="user",
                content=questionnaire_text,
                metadata={"source": "questionnaire", "agent": self.name},
            )
        self.memory_manager.ingest_questionnaire(user_id, conversation_id, questionnaire)

    def _questionnaire_to_text(self, questionnaire: dict[str, Any]) -> str:
        if not questionnaire:
            return ""

        def value(key: str) -> Any:
            item = questionnaire.get(key)
            if item in (None, "", []):
                return None
            if isinstance(item, list):
                return "、".join(str(part) for part in item if part not in (None, ""))
            return item

        pieces: list[str] = []
        if current_level := value("current_level"):
            pieces.append(f"当前最高学历是{current_level}")
        if school := value("undergraduate_school"):
            pieces.append(f"本科或当前院校是{school}")
        if major := value("undergraduate_major"):
            pieces.append(f"本科或当前专业是{major}")
        score_type = str(value("score_type") or "")
        score_value = value("score_value")
        if score_value:
            if "均分" in score_type:
                pieces.append(f"均分是{score_value}")
            else:
                pieces.append(f"GPA/绩点是{score_value}")
        language_type = value("language_type")
        language_score = value("language_score")
        if language_type or language_score:
            pieces.append(f"语言或标化成绩：{language_type or ''} {language_score or ''}".strip())
        if experiences := value("experiences"):
            pieces.append(f"申请经历包括{experiences}")
        if application_year := value("application_year"):
            pieces.append(f"计划入学年份是{application_year}")
        if countries := value("target_countries"):
            pieces.append(f"目标国家/地区是{countries}")
        if majors := value("target_majors"):
            pieces.append(f"目标专业方向是{majors}")
        if budget := value("budget"):
            pieces.append(f"预算范围是{budget}")
        if priorities := value("priorities"):
            pieces.append(f"更看重的偏好是{priorities}")
        if notes := value("extra_notes"):
            pieces.append(f"其他补充信息：{notes}")

        return "问卷信息：" + "；".join(pieces) if pieces else ""

    def _missing_fields(self, profile: dict[str, Any]) -> list[str]:
        academic = profile.get("academic") or {}
        goals = profile.get("goals") or {}
        missing = []
        if academic.get("gpa") is None and academic.get("percentage_score") is None:
            missing.append("GPA/均分")
        if not goals.get("target_countries"):
            missing.append("目标国家/地区")
        if not goals.get("target_level"):
            missing.append("申请阶段")
        if not goals.get("target_majors"):
            missing.append("目标专业")
        if not academic.get("language_scores"):
            missing.append("语言/标化成绩")
        if not goals.get("application_year"):
            missing.append("申请或入学年份")
        return missing

    def _answer(self, profile: dict[str, Any], missing: list[str]) -> str:
        name = profile.get("display_name") or "同学"
        goals = profile.get("goals") or {}
        academic = profile.get("academic") or {}
        experiences = profile.get("experiences") or {}
        target = ", ".join(goals.get("target_countries") or []) or "未明确国家"
        majors = ", ".join(goals.get("target_majors") or []) or academic.get("major") or "未明确专业"
        score = academic.get("gpa")
        if score is None:
            score = academic.get("percentage_score")
        score_label = "未填写" if score is None else str(score)
        known = [
            f"目标国家/地区: {target}",
            f"目标专业: {majors}",
            f"GPA/成绩: {score_label}",
            f"工作/项目年限: {experiences.get('work_years') or '未填写'}",
        ]
        if missing:
            return (
                f"{name}，我已经把你的画像更新好了。当前已知重点是："
                f"{'；'.join(known)}。下一步最好补充：{', '.join(missing)}。"
            )
        return f"{name}，你的画像已经比较完整：{'；'.join(known)}。后续推荐会优先按这些偏好和背景匹配真实案例。"
