# -*- coding: utf-8 -*-
"""Persistent memory for the study-abroad AI agent.

The memory layer is intentionally local and dependency-free.  It gives the
agent the same basic shape as mainstream AI products:

- multiple conversations per user
- recent-message short-term memory
- rolling conversation summary
- structured long-term user profile
- pruned, deduplicated long-term memories

LLM calls can later replace the heuristic summarizer/extractor, but the storage
and prompt contract should remain stable.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
MEMORY_DIR = BASE_DIR / "app" / "data" / "memory"
MEMORY_STORE_PATH = MEMORY_DIR / "memory_store.json"

COUNTRY_ALIASES = {
    "美国": "US",
    "美研": "US",
    "美本": "US",
    "us": "US",
    "usa": "US",
    "america": "US",
    "英国": "UK",
    "英研": "UK",
    "英本": "UK",
    "uk": "UK",
    "加拿大": "Canada",
    "canada": "Canada",
    "澳洲": "Australia",
    "澳大利亚": "Australia",
    "australia": "Australia",
    "新加坡": "Singapore",
    "singapore": "Singapore",
    "香港": "Hong Kong",
    "港校": "Hong Kong",
}

LEVEL_ALIASES = {
    "本科": "undergrad",
    "本申": "undergrad",
    "bachelor": "undergrad",
    "undergrad": "undergrad",
    "硕士": "graduate",
    "研究生": "graduate",
    "硕申": "graduate",
    "master": "graduate",
    "msc": "graduate",
    "phd": "phd",
    "博士": "phd",
}

MAJOR_ALIASES = {
    "Computer Science": ["cs", "计算机", "computer science", "软件", "人工智能", "ai", "机器学习", "数据科学"],
    "Data Science": ["数据科学", "data science", "数据分析", "analytics", "商业分析"],
    "Business": ["商科", "business", "管理", "市场", "marketing", "mim"],
    "Finance": ["金融", "finance", "fintech", "金工", "金融工程"],
    "Engineering": ["工程", "engineering", "电子", "机械", "土木", "ee", "me"],
    "Design": ["设计", "design", "交互", "ux", "艺术"],
    "Education": ["教育", "education", "tesol"],
}

PREFERENCE_ALIASES = {
    "career_outcome": ["就业", "找工作", "工作机会", "留当地工作", "career", "job"],
    "ranking": ["排名", "qs", "综排", "名校", "top"],
    "budget_sensitive": ["预算", "费用", "学费", "便宜", "性价比", "cost"],
    "scholarship": ["奖学金", "奖助", "scholarship"],
    "safety": ["保底", "稳妥", "稳一点", "低风险"],
    "ambitious": ["冲刺", "梦校", "高排名", "更好学校"],
    "location": ["地理位置", "城市", "地区", "location"],
}

PREFERENCE_LABELS = {
    "career_outcome": "就业结果",
    "ranking": "学校排名",
    "budget_sensitive": "预算/性价比",
    "scholarship": "奖学金",
    "safety": "稳妥保底",
    "ambitious": "冲刺名校",
    "location": "地理位置",
}

LOW_VALUE_UTTERANCES = {
    "好",
    "好的",
    "嗯",
    "嗯嗯",
    "谢谢",
    "可以",
    "继续",
    "ok",
    "yes",
    "no",
}

GPA_PATTERNS = [
    re.compile(r"(?:gpa|绩点|均分)\s*[:：为是]?\s*(\d(?:\.\d+)?)", re.I),
    re.compile(r"(\d(?:\.\d+)?)\s*(?:/4(?:\.0)?|绩点|gpa)", re.I),
]
IELTS_RE = re.compile(r"(?:雅思|ielts)\s*[:：]?\s*(\d+(?:\.\d+)?)", re.I)
TOEFL_RE = re.compile(r"(?:托福|toefl)\s*[:：]?\s*(\d{2,3})", re.I)
GRE_RE = re.compile(r"(?:gre)\s*[:：]?\s*(\d{3})", re.I)
GMAT_RE = re.compile(r"(?:gmat)\s*[:：]?\s*(\d{3})", re.I)
YEAR_RE = re.compile(r"(20\d{2})")
WORK_YEAR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:年|years?|yrs?)", re.I)
WORK_MONTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个月|月|months?|mos?)", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _clip(text: str, max_chars: int = 180) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _unique_extend(values: list[Any], additions: list[Any]) -> list[Any]:
    seen = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}
    for value in additions:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if value not in (None, "", []) and marker not in seen:
            values.append(value)
            seen.add(marker)
    return values


def _message_is_low_value(content: str) -> bool:
    normalized = _normalize_text(content)
    return len(normalized) <= 2 or normalized in LOW_VALUE_UTTERANCES


def _detect_countries(text: str) -> list[str]:
    lowered = text.lower()
    matches: list[tuple[int, str]] = []
    for alias, country in COUNTRY_ALIASES.items():
        pos = lowered.find(alias.lower())
        if pos >= 0:
            matches.append((pos, country))
    countries = []
    seen = set()
    for _, country in sorted(matches, key=lambda item: item[0]):
        if country not in seen:
            countries.append(country)
            seen.add(country)
    return countries


def _detect_level(text: str) -> str | None:
    lowered = text.lower()
    for alias, level in LEVEL_ALIASES.items():
        if alias.lower() in lowered:
            return level
    return None


def _detect_majors(text: str) -> list[str]:
    lowered = text.lower()
    majors = []
    for major, aliases in MAJOR_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            majors.append(major)
    return majors


def _extract_gpa(text: str) -> float | None:
    lowered = text.lower()
    if not any(marker in lowered for marker in ["gpa", "绩点", "均分"]):
        return None
    for pattern in GPA_PATTERNS:
        matches = [float(match.group(1)) for match in pattern.finditer(text)]
        plausible = [value for value in matches if 0 < value <= 4.3]
        if plausible:
            return plausible[0]
    return None


def _extract_application_year(text: str) -> int | None:
    matches = [int(match.group(1)) for match in YEAR_RE.finditer(text)]
    plausible = [value for value in matches if 2024 <= value <= 2035]
    return plausible[0] if plausible else None


def _extract_work_years(text: str) -> float | None:
    years = [float(match.group(1)) for match in WORK_YEAR_RE.finditer(text)]
    if years:
        return max(years)
    months = [float(match.group(1)) for match in WORK_MONTH_RE.finditer(text)]
    if months:
        return round(max(months) / 12, 2)
    return None


def _extract_language_scores(text: str) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    if match := IELTS_RE.search(text):
        scores["ielts"] = float(match.group(1))
    if match := TOEFL_RE.search(text):
        scores["toefl"] = int(match.group(1))
    if match := GRE_RE.search(text):
        scores["gre"] = int(match.group(1))
    if match := GMAT_RE.search(text):
        scores["gmat"] = int(match.group(1))
    return scores


def _language_key(label: str | None) -> str | None:
    normalized = (label or "").strip().lower()
    if not normalized or "暂未" in normalized:
        return None
    if "ielts" in normalized or "雅思" in normalized:
        return "ielts"
    if "toefl" in normalized or "托福" in normalized:
        return "toefl"
    if "gre" in normalized:
        return "gre"
    if "gmat" in normalized:
        return "gmat"
    return normalized


def _numeric_score(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _detect_preferences(text: str) -> list[str]:
    lowered = text.lower()
    preferences = []
    for preference, aliases in PREFERENCE_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            preferences.append(preference)
    return preferences


def _detect_preferences_from_labels(labels: list[str]) -> list[str]:
    preferences: list[str] = []
    for label in labels:
        preferences.extend(_detect_preferences(label))
        if "综合平衡" in label:
            preferences.extend(["career_outcome", "budget_sensitive", "safety"])
    return list(dict.fromkeys(preferences))


def _preference_labels(preferences: list[str]) -> list[str]:
    return [PREFERENCE_LABELS.get(item, item) for item in preferences]


def _detect_experience_flags(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "has_research": any(marker in lowered for marker in ["科研", "研究", "论文", "实验室", "research", "paper"]),
        "has_internship": any(marker in lowered for marker in ["实习", "internship", "intern"]),
        "has_work": any(marker in lowered for marker in ["工作", "全职", "毕业后", "公司", "work", "industry"]),
        "has_competition": any(marker in lowered for marker in ["竞赛", "比赛", "奥赛", "acm", "noip", "competition"]),
        "has_project": any(marker in lowered for marker in ["项目", "产品", "上线", "开源", "app", "project"]),
        "has_product": any(marker in lowered for marker in ["产品", "产品经理", "product", "pm", "0到1", "上线"]),
        "has_ai": any(marker in lowered for marker in ["ai", "人工智能", "机器学习", "深度学习", "数据"]),
    }


def _extract_display_name(text: str) -> str | None:
    patterns = [
        r"(?:我叫|叫我|我的名字是)\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,16})",
        r"(?:my name is|call me)\s+([A-Za-z0-9_\-]{1,24})",
    ]
    for pattern in patterns:
        if match := re.search(pattern, text, re.I):
            return match.group(1)
    return None


def _default_profile(display_name: str = "访客") -> dict[str, Any]:
    return {
        "display_name": display_name,
        "academic": {
            "current_level": None,
            "school": None,
            "major": None,
            "gpa": None,
            "percentage_score": None,
            "score_scale": None,
            "language_scores": {},
        },
        "goals": {
            "target_level": None,
            "target_countries": [],
            "target_majors": [],
            "application_year": None,
        },
        "experiences": {
            "work_years": None,
            "has_research": False,
            "has_internship": False,
            "has_work": False,
            "has_competition": False,
            "has_project": False,
            "has_product": False,
            "has_ai": False,
        },
        "preferences": {
            "priorities": [],
            "risk_tolerance": None,
            "budget": None,
        },
        "constraints": [],
        "notes": [],
    }


@dataclass
class MemoryContext:
    user_id: str
    conversation_id: str
    profile: dict[str, Any]
    long_term_memories: list[dict[str, Any]]
    conversation_summary: str
    recent_messages: list[dict[str, Any]]
    prompt_context: str


class MemoryManager:
    """Manage local long-term and short-term memory for users."""

    def __init__(
        self,
        store_path: Path | str = MEMORY_STORE_PATH,
        recent_message_limit: int = 14,
        max_long_term_memories: int = 80,
        summary_bullet_limit: int = 18,
    ):
        self.store_path = Path(store_path)
        self.recent_message_limit = recent_message_limit
        self.max_long_term_memories = max_long_term_memories
        self.summary_bullet_limit = summary_bullet_limit
        self.store = self._load_store()

    def _load_store(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"version": 1, "users": {}}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.store_path.with_suffix(".corrupt.json")
            self.store_path.replace(backup)
            return {"version": 1, "users": {}}
        data.setdefault("version", 1)
        data.setdefault("users", {})
        return data

    def save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.store_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.store, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.store_path)

    def get_or_create_user(self, user_id: str = "visitor", display_name: str = "访客") -> dict[str, Any]:
        users = self.store.setdefault("users", {})
        if user_id not in users:
            users[user_id] = {
                "user_id": user_id,
                "created_at": _now(),
                "updated_at": _now(),
                "profile": _default_profile(display_name),
                "memories": [],
                "conversations": {},
                "conversation_order": [],
                "active_conversation_id": None,
            }
        user = users[user_id]
        user.setdefault("profile", _default_profile(display_name))
        user.setdefault("memories", [])
        user.setdefault("conversations", {})
        user.setdefault("conversation_order", [])
        user.setdefault("active_conversation_id", None)
        return user

    def create_conversation(
        self,
        user_id: str = "visitor",
        title: str | None = None,
        entry_point: str = "chat",
        set_active: bool = True,
    ) -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        conversation_id = _new_id("conv")
        conversation = {
            "conversation_id": conversation_id,
            "title": title or "新的留学咨询",
            "entry_point": entry_point,
            "created_at": _now(),
            "updated_at": _now(),
            "summary": "",
            "summary_bullets": [],
            "messages": [],
        }
        user["conversations"][conversation_id] = conversation
        user["conversation_order"].insert(0, conversation_id)
        if set_active:
            user["active_conversation_id"] = conversation_id
        user["updated_at"] = _now()
        self.save()
        return deepcopy(conversation)

    def get_conversation(self, user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        if conversation_id is None:
            conversation_id = user.get("active_conversation_id")
        if not conversation_id:
            created = self.create_conversation(user_id=user_id)
            return self.store["users"][user_id]["conversations"][created["conversation_id"]]
        conversation = user["conversations"].get(conversation_id)
        if not conversation:
            created = self.create_conversation(user_id=user_id)
            return self.store["users"][user_id]["conversations"][created["conversation_id"]]
        return conversation

    def list_conversations(self, user_id: str = "visitor") -> list[dict[str, Any]]:
        user = self.get_or_create_user(user_id)
        conversations = user.get("conversations", {})
        ordered = []
        for conversation_id in user.get("conversation_order", []):
            if conversation_id in conversations:
                item = deepcopy(conversations[conversation_id])
                item["message_count"] = len(item.get("messages") or [])
                ordered.append(item)
        return ordered

    def set_active_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        if conversation_id not in user["conversations"]:
            raise KeyError(f"Conversation not found: {conversation_id}")
        user["active_conversation_id"] = conversation_id
        user["updated_at"] = _now()
        self.save()
        return deepcopy(user["conversations"][conversation_id])

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        user = self.get_or_create_user(user_id)
        existed = user["conversations"].pop(conversation_id, None) is not None
        user["conversation_order"] = [item for item in user["conversation_order"] if item != conversation_id]
        if user.get("active_conversation_id") == conversation_id:
            user["active_conversation_id"] = user["conversation_order"][0] if user["conversation_order"] else None
        if existed:
            user["updated_at"] = _now()
            self.save()
        return existed

    def append_message(
        self,
        user_id: str,
        conversation_id: str | None,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError(f"Unsupported role: {role}")
        if not content or not content.strip():
            raise ValueError("Message content cannot be empty")

        user = self.get_or_create_user(user_id)
        conversation = self.get_conversation(user_id, conversation_id)
        conversation_id = conversation["conversation_id"]
        message = {
            "message_id": _new_id("msg"),
            "role": role,
            "content": content.strip(),
            "created_at": _now(),
            "metadata": metadata or {},
        }
        conversation["messages"].append(message)
        conversation["updated_at"] = _now()
        user["updated_at"] = _now()

        if role == "user":
            self._maybe_update_title(conversation, content)
            self._ingest_user_message(user, conversation, content)

        self._update_conversation_summary(conversation, message)
        self.prune(user_id=user_id, conversation_id=conversation_id, save=False)
        self._touch_conversation_order(user, conversation_id)
        self.save()
        return deepcopy(message)

    def ingest_questionnaire(self, user_id: str, conversation_id: str, questionnaire: dict[str, Any]) -> None:
        """Persist structured questionnaire data without relying only on text extraction."""
        if not questionnaire:
            return

        user = self.get_or_create_user(user_id)
        conversation = self.get_conversation(user_id, conversation_id)
        updates = self._questionnaire_profile_updates(questionnaire)
        self._merge_profile_updates(user["profile"], updates)

        note = self._questionnaire_note(questionnaire)
        if note:
            user["profile"].setdefault("notes", [])
            if note not in user["profile"]["notes"]:
                user["profile"]["notes"].append(note)

        for item in self._extract_memory_items(note or "用户提交了选校问卷", updates, conversation["conversation_id"]):
            self._upsert_memory(user, item)
        self._touch_conversation_order(user, conversation["conversation_id"])
        user["updated_at"] = _now()
        self.save()

    def _questionnaire_profile_updates(self, questionnaire: dict[str, Any]) -> dict[str, Any]:
        def value(key: str) -> Any:
            item = questionnaire.get(key)
            if item in (None, "", []):
                return None
            return item

        updates: dict[str, Any] = {}
        academic: dict[str, Any] = {}
        goals: dict[str, Any] = {}
        experiences: dict[str, Any] = {}
        preferences: dict[str, Any] = {}

        if current_level := value("current_level"):
            academic["current_level"] = str(current_level)
            if "本科" in str(current_level) or "硕士" in str(current_level):
                goals["target_level"] = "graduate"
        if school := value("undergraduate_school"):
            academic["school"] = str(school)
        if major := value("undergraduate_major"):
            academic["major"] = str(major)

        score_type = str(value("score_type") or "")
        score_value = _numeric_score(value("score_value"))
        if score_value is not None:
            if "均分" in score_type or score_value > 4.3:
                academic["percentage_score"] = score_value
                academic["score_scale"] = "percentage"
            else:
                academic["gpa"] = score_value
                academic["score_scale"] = "4.0"

        language_key = _language_key(str(value("language_type") or ""))
        language_score = _numeric_score(value("language_score"))
        if language_key and language_score is not None:
            academic["language_scores"] = {
                language_key: int(language_score) if language_key in {"toefl", "gre", "gmat"} else language_score
            }

        for item in value("experiences") or []:
            label = str(item)
            if "暂时没有" in label:
                continue
            flags = _detect_experience_flags(label)
            for key, flag in flags.items():
                experiences[key] = experiences.get(key, False) or flag
            if "工作经历" in label:
                experiences["has_work"] = True

        if application_year := value("application_year"):
            year = _extract_application_year(str(application_year))
            if year:
                goals["application_year"] = year

        countries = []
        for item in value("target_countries") or []:
            countries.extend(_detect_countries(str(item)))
        if countries:
            goals["target_countries"] = list(dict.fromkeys(countries))

        majors = []
        for item in value("target_majors") or []:
            majors.extend(_detect_majors(str(item)))
        if majors:
            goals["target_majors"] = list(dict.fromkeys(majors))
            academic.setdefault("major", majors[0])
            goals.setdefault("target_level", "graduate")

        budget = value("budget")
        if budget:
            preferences["budget"] = list(budget) if isinstance(budget, list) else [str(budget)]
            preferences.setdefault("priorities", [])
            if any("暂不确定" not in str(item) for item in preferences["budget"]):
                preferences["priorities"].append("budget_sensitive")

        priority_labels = [str(item) for item in (value("priorities") or [])]
        priorities = _detect_preferences_from_labels(priority_labels)
        if priorities:
            preferences.setdefault("priorities", [])
            preferences["priorities"].extend(priorities)

        if notes := value("extra_notes"):
            text_updates = self._extract_profile_updates(str(notes))
            for section, payload in text_updates.items():
                if section == "academic":
                    academic.update(payload)
                elif section == "goals":
                    goals.update(payload)
                elif section == "experiences":
                    experiences.update(payload)
                elif section == "preferences":
                    preferences.setdefault("priorities", [])
                    preferences["priorities"].extend(payload.get("priorities") or [])

        if academic:
            updates["academic"] = academic
        if goals:
            updates["goals"] = goals
        if experiences:
            updates["experiences"] = experiences
        if preferences:
            if preferences.get("priorities"):
                preferences["priorities"] = list(dict.fromkeys(preferences["priorities"]))
            updates["preferences"] = preferences
        return updates

    def _questionnaire_note(self, questionnaire: dict[str, Any]) -> str:
        visible = {key: value for key, value in questionnaire.items() if value not in (None, "", [])}
        if not visible:
            return ""
        return "问卷信息：" + json.dumps(visible, ensure_ascii=False, sort_keys=True)

    def record_turn(
        self,
        user_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_msg = self.append_message(user_id, conversation_id, "user", user_message, metadata=metadata)
        conversation = self.get_conversation(user_id, conversation_id)
        self.append_message(user_id, conversation["conversation_id"], "assistant", assistant_message, metadata=metadata)
        return user_msg

    def _touch_conversation_order(self, user: dict[str, Any], conversation_id: str) -> None:
        order = [item for item in user.get("conversation_order", []) if item != conversation_id]
        order.insert(0, conversation_id)
        user["conversation_order"] = order
        user["active_conversation_id"] = conversation_id

    def _maybe_update_title(self, conversation: dict[str, Any], content: str) -> None:
        if conversation.get("title") and conversation["title"] != "新的留学咨询":
            return
        title = _clip(content, 24)
        conversation["title"] = title or "新的留学咨询"

    def _ingest_user_message(self, user: dict[str, Any], conversation: dict[str, Any], content: str) -> None:
        if _message_is_low_value(content):
            return

        profile_updates = self._extract_profile_updates(content)
        self._merge_profile_updates(user["profile"], profile_updates)
        memory_items = self._extract_memory_items(content, profile_updates, conversation["conversation_id"])
        for item in memory_items:
            self._upsert_memory(user, item)

    def _extract_profile_updates(self, content: str) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if name := _extract_display_name(content):
            updates["display_name"] = name

        countries = _detect_countries(content)
        if countries:
            updates.setdefault("goals", {})["target_countries"] = countries

        level = _detect_level(content)
        if level:
            updates.setdefault("goals", {})["target_level"] = level

        majors = _detect_majors(content)
        if majors:
            updates.setdefault("goals", {})["target_majors"] = majors
            updates.setdefault("academic", {})["major"] = majors[0]

        if gpa := _extract_gpa(content):
            updates.setdefault("academic", {})["gpa"] = gpa

        if scores := _extract_language_scores(content):
            updates.setdefault("academic", {})["language_scores"] = scores

        if year := _extract_application_year(content):
            updates.setdefault("goals", {})["application_year"] = year

        work_years = _extract_work_years(content)
        experience_flags = _detect_experience_flags(content)
        if work_years is not None or any(experience_flags.values()):
            updates.setdefault("experiences", {}).update(experience_flags)
            if work_years is not None:
                updates["experiences"]["work_years"] = work_years

        preferences = _detect_preferences(content)
        if preferences:
            updates.setdefault("preferences", {})["priorities"] = preferences

        return updates

    def _merge_profile_updates(self, profile: dict[str, Any], updates: dict[str, Any]) -> None:
        if not updates:
            return
        if updates.get("display_name"):
            profile["display_name"] = updates["display_name"]

        academic = updates.get("academic") or {}
        for key, value in academic.items():
            if key == "language_scores":
                profile["academic"].setdefault("language_scores", {}).update(value)
            elif value not in (None, "", []):
                profile["academic"][key] = value

        goals = updates.get("goals") or {}
        if goals.get("target_countries"):
            _unique_extend(profile["goals"].setdefault("target_countries", []), goals["target_countries"])
        if goals.get("target_majors"):
            _unique_extend(profile["goals"].setdefault("target_majors", []), goals["target_majors"])
        for key in ("target_level", "application_year"):
            if goals.get(key) not in (None, "", []):
                profile["goals"][key] = goals[key]

        experiences = updates.get("experiences") or {}
        for key, value in experiences.items():
            if key == "work_years" and value is not None:
                existing = profile["experiences"].get("work_years")
                profile["experiences"]["work_years"] = max(existing or 0, value)
            elif isinstance(value, bool):
                profile["experiences"][key] = profile["experiences"].get(key, False) or value

        priorities = (updates.get("preferences") or {}).get("priorities") or []
        if priorities:
            _unique_extend(profile["preferences"].setdefault("priorities", []), priorities)
        budget = (updates.get("preferences") or {}).get("budget")
        if budget not in (None, "", []):
            profile["preferences"]["budget"] = budget

    def _extract_memory_items(
        self,
        content: str,
        updates: dict[str, Any],
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        def add(kind: str, content_text: str, importance: float, tags: list[str] | None = None) -> None:
            normalized = _normalize_text(f"{kind}:{content_text}")
            memory_id = "mem_" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:14]
            items.append(
                {
                    "memory_id": memory_id,
                    "kind": kind,
                    "content": content_text,
                    "importance": importance,
                    "confidence": 0.82,
                    "usage_count": 1,
                    "created_at": _now(),
                    "last_seen_at": _now(),
                    "source_conversation_id": conversation_id,
                    "tags": tags or [],
                }
            )

        if updates.get("display_name"):
            add("identity", f"用户希望被称为 {updates['display_name']}", 0.95, ["profile"])

        academic = updates.get("academic") or {}
        if academic.get("gpa") is not None:
            add("academic", f"用户 GPA/绩点为 {academic['gpa']}", 0.9, ["academic"])
        if academic.get("percentage_score") is not None:
            add("academic", f"用户百分制成绩为 {academic['percentage_score']}", 0.86, ["academic"])
        if academic.get("school"):
            add("academic", f"用户本科或当前院校为 {academic['school']}", 0.74, ["academic"])
        if academic.get("current_level"):
            add("academic", f"用户当前最高学历为 {academic['current_level']}", 0.72, ["academic"])
        if academic.get("major"):
            add("academic", f"用户关注或背景专业为 {academic['major']}", 0.78, ["major"])
        for test_name, score in (academic.get("language_scores") or {}).items():
            add("language", f"用户 {test_name.upper()} 成绩为 {score}", 0.78, ["language"])

        goals = updates.get("goals") or {}
        if goals.get("target_countries"):
            add("goal", f"用户目标国家/地区包括 {', '.join(goals['target_countries'])}", 0.9, ["country"])
        if goals.get("target_level"):
            add("goal", f"用户目标申请阶段为 {goals['target_level']}", 0.88, ["level"])
        if goals.get("target_majors"):
            add("goal", f"用户目标专业方向包括 {', '.join(goals['target_majors'])}", 0.88, ["major"])
        if goals.get("application_year"):
            add("goal", f"用户计划 {goals['application_year']} 年申请或入学", 0.75, ["timeline"])

        experiences = updates.get("experiences") or {}
        if experiences.get("work_years") is not None:
            add("experience", f"用户有约 {experiences['work_years']} 年工作/项目经历", 0.86, ["experience", "work"])
        for flag, label in [
            ("has_research", "科研/论文经历"),
            ("has_internship", "实习经历"),
            ("has_competition", "竞赛经历"),
            ("has_project", "项目/产品落地经历"),
            ("has_product", "产品经历"),
            ("has_ai", "AI/数据相关经历"),
        ]:
            if experiences.get(flag):
                add("experience", f"用户提到自己有{label}", 0.74, ["experience"])

        priorities = (updates.get("preferences") or {}).get("priorities") or []
        if priorities:
            add("preference", f"用户偏好/关注点包括 {', '.join(_preference_labels(priorities))}", 0.76, ["preference"])
        budget = (updates.get("preferences") or {}).get("budget")
        if budget:
            rendered_budget = "、".join(str(item) for item in budget) if isinstance(budget, list) else str(budget)
            add("preference", f"用户预算范围为 {rendered_budget}", 0.8, ["preference", "budget"])

        if not items and len(content) >= 18:
            add("note", f"用户补充：{_clip(content, 140)}", 0.42, ["note"])

        return items

    def _upsert_memory(self, user: dict[str, Any], new_item: dict[str, Any]) -> None:
        memories = user.setdefault("memories", [])
        for item in memories:
            if item.get("memory_id") == new_item["memory_id"]:
                item["importance"] = max(float(item.get("importance", 0)), new_item["importance"])
                item["confidence"] = max(float(item.get("confidence", 0)), new_item["confidence"])
                item["usage_count"] = int(item.get("usage_count", 0)) + 1
                item["last_seen_at"] = _now()
                item["tags"] = sorted(set((item.get("tags") or []) + (new_item.get("tags") or [])))
                return
        memories.append(new_item)

    def _update_conversation_summary(self, conversation: dict[str, Any], message: dict[str, Any]) -> None:
        content = message.get("content", "")
        if _message_is_low_value(content):
            return

        role = message.get("role")
        prefix = "用户提到" if role == "user" else "已回复"
        if role not in {"user", "assistant"}:
            return
        if role == "assistant" and not any(marker in content for marker in ["建议", "推荐", "路线", "学校", "专业", "申请", "案例"]):
            return

        bullet = f"{prefix}: {_clip(content, 140)}"
        bullets = conversation.setdefault("summary_bullets", [])
        if bullet not in bullets:
            bullets.append(bullet)
        conversation["summary_bullets"] = bullets[-self.summary_bullet_limit :]
        conversation["summary"] = "；".join(conversation["summary_bullets"][-10:])

    def prune(self, user_id: str = "visitor", conversation_id: str | None = None, save: bool = True) -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        removed_messages = 0
        removed_memories = 0

        conversations = user.get("conversations", {})
        target_ids = [conversation_id] if conversation_id else list(conversations.keys())
        for conv_id in target_ids:
            conversation = conversations.get(conv_id)
            if not conversation:
                continue
            messages = conversation.get("messages") or []
            if len(messages) > self.recent_message_limit:
                removed_messages += len(messages) - self.recent_message_limit
                conversation["messages"] = messages[-self.recent_message_limit :]

        memories = user.get("memories") or []
        deduped: dict[str, dict[str, Any]] = {}
        for item in memories:
            key = item.get("memory_id") or hashlib.sha1(_normalize_text(item.get("content", "")).encode("utf-8")).hexdigest()
            if key not in deduped:
                deduped[key] = item
            else:
                kept = deduped[key]
                kept["importance"] = max(float(kept.get("importance", 0)), float(item.get("importance", 0)))
                kept["confidence"] = max(float(kept.get("confidence", 0)), float(item.get("confidence", 0)))
                kept["usage_count"] = int(kept.get("usage_count", 0)) + int(item.get("usage_count", 1))
                kept["last_seen_at"] = max(str(kept.get("last_seen_at", "")), str(item.get("last_seen_at", "")))
                removed_memories += 1

        scored = sorted(deduped.values(), key=self._memory_rank_score, reverse=True)
        kept = self._balanced_memory_keep(scored)
        removed_memories += max(0, len(scored) - len(kept))
        user["memories"] = kept

        if save:
            user["updated_at"] = _now()
            self.save()
        return {"removed_messages": removed_messages, "removed_memories": removed_memories}

    def _memory_rank_score(self, item: dict[str, Any]) -> float:
        importance = float(item.get("importance", 0.0))
        confidence = float(item.get("confidence", 0.0))
        usage_count = int(item.get("usage_count", 0))
        recency_bonus = 0.15 if item.get("last_seen_at") == item.get("created_at") else 0.3
        return importance * 2.0 + confidence + min(usage_count, 8) * 0.12 + recency_bonus

    def _balanced_memory_keep(self, scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(scored) <= self.max_long_term_memories:
            return scored

        minimum_by_kind = {
            "identity": 1,
            "preference": 2,
            "goal": 2,
            "academic": 1,
            "experience": 2,
            "language": 1,
        }
        kept: list[dict[str, Any]] = []
        kept_ids: set[str] = set()

        def remember(item: dict[str, Any]) -> bool:
            memory_id = item.get("memory_id") or item.get("content")
            if memory_id in kept_ids or len(kept) >= self.max_long_term_memories:
                return False
            kept.append(item)
            kept_ids.add(memory_id)
            return True

        for kind, minimum in minimum_by_kind.items():
            count = 0
            for item in scored:
                if item.get("kind") == kind and remember(item):
                    count += 1
                    if count >= minimum:
                        break

        for item in scored:
            remember(item)
            if len(kept) >= self.max_long_term_memories:
                break

        return sorted(kept, key=self._memory_rank_score, reverse=True)

    def forget_memory(self, user_id: str, memory_id_or_text: str) -> int:
        user = self.get_or_create_user(user_id)
        needle = _normalize_text(memory_id_or_text)
        kept = []
        removed = 0
        for item in user.get("memories") or []:
            haystacks = [
                _normalize_text(item.get("memory_id", "")),
                _normalize_text(item.get("content", "")),
                _normalize_text(",".join(item.get("tags") or [])),
            ]
            if any(needle and needle in haystack for haystack in haystacks):
                removed += 1
            else:
                kept.append(item)
        user["memories"] = kept
        if removed:
            user["updated_at"] = _now()
            self.save()
        return removed

    def clear_user_memory(self, user_id: str, keep_conversations: bool = True) -> None:
        user = self.get_or_create_user(user_id)
        display_name = user.get("profile", {}).get("display_name", "访客")
        user["profile"] = _default_profile(display_name)
        user["memories"] = []
        if not keep_conversations:
            user["conversations"] = {}
            user["conversation_order"] = []
            user["active_conversation_id"] = None
        user["updated_at"] = _now()
        self.save()

    def export_user_profile(self, user_id: str = "visitor") -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        return deepcopy(user["profile"])

    def build_prompt_context(
        self,
        user_id: str = "visitor",
        conversation_id: str | None = None,
        current_query: str = "",
        recent_turns: int = 6,
        max_memories: int = 12,
    ) -> MemoryContext:
        user = self.get_or_create_user(user_id)
        conversation = self.get_conversation(user_id, conversation_id)
        query_tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2}", current_query.lower()))
        selected_memories = self._select_relevant_memories(user.get("memories") or [], query_tokens, max_memories)
        recent_messages = (conversation.get("messages") or [])[-recent_turns * 2 :]
        prompt_context = self._format_prompt_context(
            profile=user["profile"],
            memories=selected_memories,
            summary=conversation.get("summary", ""),
            recent_messages=recent_messages,
        )
        return MemoryContext(
            user_id=user_id,
            conversation_id=conversation["conversation_id"],
            profile=deepcopy(user["profile"]),
            long_term_memories=deepcopy(selected_memories),
            conversation_summary=conversation.get("summary", ""),
            recent_messages=deepcopy(recent_messages),
            prompt_context=prompt_context,
        )

    def _select_relevant_memories(
        self,
        memories: list[dict[str, Any]],
        query_tokens: set[str],
        max_memories: int,
    ) -> list[dict[str, Any]]:
        def score(item: dict[str, Any]) -> float:
            content = item.get("content", "").lower()
            tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2}", content))
            overlap = len(tokens & query_tokens) / max(len(query_tokens), 1)
            return self._memory_rank_score(item) + overlap * 1.5

        return sorted(memories, key=score, reverse=True)[:max_memories]

    def _format_prompt_context(
        self,
        profile: dict[str, Any],
        memories: list[dict[str, Any]],
        summary: str,
        recent_messages: list[dict[str, Any]],
    ) -> str:
        profile_lines = self._profile_to_lines(profile)
        memory_lines = [f"- {item.get('content')}" for item in memories]
        recent_lines = [
            f"{message.get('role')}: {_clip(message.get('content', ''), 220)}"
            for message in recent_messages
            if message.get("role") in {"user", "assistant"}
        ]
        sections = [
            "【长期用户画像】\n" + ("\n".join(profile_lines) if profile_lines else "- 暂无稳定画像"),
            "【长期记忆】\n" + ("\n".join(memory_lines) if memory_lines else "- 暂无可用长期记忆"),
            "【当前会话摘要】\n" + (summary or "暂无摘要"),
            "【最近对话窗口】\n" + ("\n".join(recent_lines) if recent_lines else "暂无最近对话"),
        ]
        return "\n\n".join(sections)

    def _profile_to_lines(self, profile: dict[str, Any]) -> list[str]:
        lines = [f"- 称呼: {profile.get('display_name') or '访客'}"]
        academic = profile.get("academic") or {}
        goals = profile.get("goals") or {}
        experiences = profile.get("experiences") or {}
        preferences = profile.get("preferences") or {}

        if academic.get("major"):
            lines.append(f"- 背景/关注专业: {academic['major']}")
        if academic.get("school"):
            lines.append(f"- 本科/当前院校: {academic['school']}")
        if academic.get("current_level"):
            lines.append(f"- 当前最高学历: {academic['current_level']}")
        if academic.get("gpa") is not None:
            lines.append(f"- GPA/绩点: {academic['gpa']}")
        if academic.get("percentage_score") is not None:
            lines.append(f"- 百分制成绩: {academic['percentage_score']}")
        if academic.get("language_scores"):
            rendered = ", ".join(f"{key.upper()} {value}" for key, value in academic["language_scores"].items())
            lines.append(f"- 语言/标化: {rendered}")
        if goals.get("target_level"):
            lines.append(f"- 目标阶段: {goals['target_level']}")
        if goals.get("target_countries"):
            lines.append(f"- 目标国家/地区: {', '.join(goals['target_countries'])}")
        if goals.get("target_majors"):
            lines.append(f"- 目标专业: {', '.join(goals['target_majors'])}")
        if goals.get("application_year"):
            lines.append(f"- 计划年份: {goals['application_year']}")
        if experiences.get("work_years"):
            lines.append(f"- 工作/项目年限: {experiences['work_years']} 年")

        flags = [
            label
            for key, label in [
                ("has_research", "科研"),
                ("has_internship", "实习"),
                ("has_work", "工作"),
                ("has_competition", "竞赛"),
                ("has_project", "项目"),
                ("has_product", "产品"),
                ("has_ai", "AI/数据"),
            ]
            if experiences.get(key)
        ]
        if flags:
            lines.append(f"- 经历标签: {', '.join(flags)}")
        if preferences.get("priorities"):
            lines.append(f"- 偏好重点: {', '.join(_preference_labels(preferences['priorities']))}")
        if preferences.get("budget"):
            budget = preferences["budget"]
            rendered_budget = "、".join(str(item) for item in budget) if isinstance(budget, list) else str(budget)
            lines.append(f"- 预算范围: {rendered_budget}")
        return lines


def get_memory_manager(**kwargs: Any) -> MemoryManager:
    return MemoryManager(**kwargs)


if __name__ == "__main__":
    manager = MemoryManager()
    conversation = manager.get_conversation("visitor")
    context = manager.build_prompt_context("visitor", conversation["conversation_id"])
    print(context.prompt_context)
