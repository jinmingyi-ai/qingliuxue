# -*- coding: utf-8 -*-
"""Build a local hybrid RAG index for study-abroad case retrieval.

The source data is already structured as a small knowledge graph.  For this
project a local, deterministic index is more useful than a fragile remote
embedding pipeline: we can combine metadata filtering, BM25-style sparse
retrieval, and graph relationships with predictable behavior.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_PATH = BASE_DIR / "app" / "data" / "profiles" / "cases.json"
LEGACY_CHROMA_DIR = BASE_DIR / "app" / "data" / "chroma_db"
INDEX_DIR = BASE_DIR / "app" / "data" / "rag_index"
INDEX_PATH = INDEX_DIR / "index.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{1,2}")

COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "america": "US",
    "american": "US",
    "美国": "US",
    "美本": "US",
    "美研": "US",
    "uk": "UK",
    "英国": "UK",
    "英本": "UK",
    "英研": "UK",
    "australia": "Australia",
    "澳洲": "Australia",
    "澳大利亚": "Australia",
    "canada": "Canada",
    "加拿大": "Canada",
}

LEVEL_ALIASES = {
    "undergrad": "undergrad",
    "undergraduate": "undergrad",
    "bachelor": "undergrad",
    "本科": "undergrad",
    "本申": "undergrad",
    "graduate": "graduate",
    "master": "graduate",
    "masters": "graduate",
    "msc": "graduate",
    "硕士": "graduate",
    "研究生": "graduate",
    "研申": "graduate",
}

STRATEGY_ALIASES = {
    "competition": ["竞赛", "奥赛", "NOIP", "ACM", "比赛", "建模", "competition"],
    "research": ["科研", "研究", "论文", "顶会", "实验室", "research"],
    "work": ["工作", "实习", "产业", "公司", "职业", "work", "internship", "industry"],
    "project": ["项目", "落地", "产品", "开源", "app", "系统", "project", "open source"],
    "leadership": ["领导", "团队", "学生会", "组织", "leadership"],
    "self_learning": ["自学", "逆袭", "普通高中", "背景一般", "resilience", "self"],
    "social_impact": ["公益", "社会", "教育公平", "支教", "impact"],
    "international": ["国际课程", "A-Level", "AP", "OSSD", "国际视野", "international"],
}

FIELD_WEIGHTS = {
    "identity": 4,
    "metadata": 4,
    "input": 4,
    "outcome": 4,
    "strategies": 5,
    "lessons": 5,
    "notes": 4,
    "timeline": 2,
    "relationships": 3,
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "；".join(_flatten_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _flatten_text(item)
            if text:
                parts.append(f"{key}: {text}")
        return "；".join(parts)
    return str(value)


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text for sparse retrieval."""
    text = (text or "").lower()
    tokens = TOKEN_RE.findall(text)
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2}", token):
            expanded.extend(token)
    return expanded


def _weighted_tokens(fields: dict[str, str]) -> list[str]:
    tokens: list[str] = []
    for field, text in fields.items():
        weight = FIELD_WEIGHTS.get(field, 1)
        field_tokens = tokenize(text)
        for _ in range(weight):
            tokens.extend(field_tokens)
    return tokens


def _extract_gpa(input_attrs: dict[str, Any]) -> float | None:
    for key in ("gpa", "undergrad_gpa"):
        value = input_attrs.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"\d+(?:\.\d+)?", value)
            if match:
                return float(match.group())
    return None


def _extract_work_years(work_text: str) -> float | None:
    years = [float(match.group(1)) for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:年|years?|yrs?)", work_text, re.I)]
    if years:
        return max(years)

    months = [
        float(match.group(1))
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:个月|月|months?|mos?)", work_text, re.I)
    ]
    if months:
        return round(max(months) / 12, 2)
    return None


def _detect_work_signals(input_attrs: dict[str, Any]) -> dict[str, Any]:
    work_text = _flatten_text(input_attrs.get("work_experience"))
    combined_text = " ".join(
        [
            work_text,
            _flatten_text(input_attrs.get("research_experience")),
            _flatten_text(input_attrs.get("extracurricular")),
        ]
    )
    lowered = combined_text.lower()
    work_years = _extract_work_years(work_text)
    has_internship = any(marker in lowered for marker in ["实习", "internship", "intern"])
    has_product = any(
        marker in lowered
        for marker in ["产品", "product", "pm", "产品经理", "负责人", "0到1", "上线", "用户", "月活"]
    )
    has_ai = any(marker in lowered for marker in ["ai", "人工智能", "机器学习", "深度学习", "推荐系统", "数据"])
    has_full_time = bool(work_years and work_years >= 1 and any(marker in lowered for marker in ["毕业后", "工作", "担任", "负责人", "经理"]))
    return {
        "work_years": work_years,
        "has_full_time_work": has_full_time,
        "has_internship": has_internship,
        "has_internship_only": bool(has_internship and (work_years is None or work_years < 1)),
        "has_product_experience": has_product,
        "has_ai_experience": has_ai,
    }


def _gpa_bucket(gpa: float | None) -> str | None:
    if gpa is None:
        return None
    if gpa >= 3.85:
        return "high"
    if gpa >= 3.65:
        return "mid_high"
    if gpa >= 3.45:
        return "mid"
    return "low"


def _detect_strategy_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, aliases in STRATEGY_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            tags.append(tag)
    return sorted(set(tags))


def _relationship_summary(relationships: list[dict[str, Any]], node_id: str) -> tuple[str, list[str]]:
    applied = []
    chunks = []
    for rel in relationships:
        if rel.get("start_node_id") != node_id:
            continue
        target = rel.get("end_node_id")
        if not target:
            continue
        result = (rel.get("properties") or {}).get("result")
        applied.append(str(target))
        chunks.append(f"{rel.get('type', 'RELATED_TO')} {target} result={result}")
    return "；".join(chunks), applied


def load_graph(path: Path = DATA_PATH) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for item_index, item in enumerate(data):
        relationships.extend(item.get("relationships", []))
        for node in item.get("nodes", []):
            if node.get("label") != "StudentProfile":
                continue
            profile = dict(node.get("properties") or {})
            profile["_node_id"] = node.get("id") or profile.get("profile_id")
            profile["_case_key"] = f"{profile.get('profile_id', 'profile')}::{profile['_node_id']}::{item_index}"
            profiles.append(profile)

    return profiles, relationships


def profile_to_document(profile: dict[str, Any], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    input_attrs = profile.get("input_attributes") or {}
    final_outcome = profile.get("final_outcome") or {}
    china_notes = profile.get("china_specific_notes") or {}
    rel_text, applied_program_ids = _relationship_summary(relationships, profile["_node_id"])

    admitted_schools = _as_list(final_outcome.get("admitted_schools"))
    rejected = _as_list(final_outcome.get("rejected_or_waitlist"))
    target_countries = _as_list(profile.get("target_countries")) or [profile.get("country")]
    gpa = _extract_gpa(input_attrs)
    work_signals = _detect_work_signals(input_attrs)

    fields = {
        "identity": " ".join(
            str(part)
            for part in [
                profile.get("profile_id"),
                profile.get("name"),
                profile.get("category"),
                profile.get("level"),
                profile.get("country"),
                profile.get("major"),
            ]
            if part
        ),
        "metadata": _flatten_text(
            {
                "target_countries": target_countries,
                "major": profile.get("major"),
                "difficulty": profile.get("overall_difficulty_rating"),
                "scholarship": profile.get("scholarship_obtained"),
                "work_signals": work_signals,
            }
        ),
        "input": _flatten_text(input_attrs),
        "outcome": _flatten_text(final_outcome),
        "strategies": _flatten_text(profile.get("key_strategies")),
        "lessons": _flatten_text(profile.get("lessons")),
        "notes": _flatten_text(china_notes),
        "timeline": _flatten_text(profile.get("timeline_followed")),
        "relationships": rel_text + " " + _flatten_text(profile.get("applied_programs")),
    }
    full_text = "\n".join(f"{key}: {value}" for key, value in fields.items() if value)
    strategy_tags = _detect_strategy_tags(full_text)

    metadata = {
        "case_key": profile["_case_key"],
        "profile_id": profile.get("profile_id"),
        "node_id": profile.get("_node_id"),
        "name": profile.get("name"),
        "level": profile.get("level"),
        "country": profile.get("country"),
        "category": profile.get("category"),
        "major": profile.get("major"),
        "target_countries": target_countries,
        "gpa": gpa,
        "gpa_bucket": _gpa_bucket(gpa),
        "admitted_schools": admitted_schools,
        "rejected_or_waitlist": rejected,
        "final_choice": final_outcome.get("final_choice"),
        "applied_program_ids": applied_program_ids,
        "strategy_tags": strategy_tags,
        "scholarship_obtained": bool(profile.get("scholarship_obtained")),
        "scholarship_amount_usd": profile.get("scholarship_amount_usd"),
        **work_signals,
    }

    return {
        "id": profile["_case_key"],
        "metadata": metadata,
        "fields": fields,
        "text": full_text,
        "tokens": _weighted_tokens(fields),
        "raw_profile": profile,
    }


def build_index(
    data_path: Path = DATA_PATH,
    index_path: Path = INDEX_PATH,
    remove_legacy_chroma: bool = True,
) -> dict[str, Any]:
    profiles, relationships = load_graph(data_path)
    docs = [profile_to_document(profile, relationships) for profile in profiles]

    document_frequency: Counter[str] = Counter()
    token_counts = []
    for doc in docs:
        counts = Counter(doc["tokens"])
        doc["token_counts"] = dict(counts)
        doc["length"] = sum(counts.values())
        token_counts.append(doc["length"])
        document_frequency.update(counts.keys())
        doc.pop("tokens", None)

    average_length = sum(token_counts) / max(len(token_counts), 1)
    idf = {
        token: math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
        for token, df in document_frequency.items()
    }

    graph_neighbors: dict[str, list[str]] = defaultdict(list)
    program_to_cases: dict[str, list[str]] = defaultdict(list)
    strategy_to_cases: dict[str, list[str]] = defaultdict(list)
    school_to_cases: dict[str, list[str]] = defaultdict(list)

    for doc in docs:
        case_id = doc["id"]
        meta = doc["metadata"]
        for program in meta.get("applied_program_ids") or []:
            program_to_cases[program].append(case_id)
        for tag in meta.get("strategy_tags") or []:
            strategy_to_cases[tag].append(case_id)
        for school in meta.get("admitted_schools") or []:
            normalized = str(school).lower()
            school_to_cases[normalized].append(case_id)

    for case_ids in list(program_to_cases.values()) + list(strategy_to_cases.values()) + list(school_to_cases.values()):
        for case_id in case_ids:
            graph_neighbors[case_id].extend(other for other in case_ids if other != case_id)

    index = {
        "version": 1,
        "source": str(data_path),
        "documents": docs,
        "stats": {
            "document_count": len(docs),
            "average_length": average_length,
            "idf": idf,
        },
        "graph": {
            "neighbors": {case_id: sorted(set(neighbors)) for case_id, neighbors in graph_neighbors.items()},
            "program_to_cases": {key: sorted(set(value)) for key, value in program_to_cases.items()},
            "strategy_to_cases": {key: sorted(set(value)) for key, value in strategy_to_cases.items()},
            "school_to_cases": {key: sorted(set(value)) for key, value in school_to_cases.items()},
        },
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    if remove_legacy_chroma and LEGACY_CHROMA_DIR.exists():
        shutil.rmtree(LEGACY_CHROMA_DIR)

    return index


def main() -> None:
    index = build_index()
    print(f"Built hybrid RAG index: {INDEX_PATH}")
    print(f"Documents: {index['stats']['document_count']}")
    print(f"Legacy Chroma removed: {not LEGACY_CHROMA_DIR.exists()}")


if __name__ == "__main__":
    main()
