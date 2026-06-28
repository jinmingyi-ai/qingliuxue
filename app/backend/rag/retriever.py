# -*- coding: utf-8 -*-
"""Hybrid retriever for study-abroad student route cases."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .vector_store import (
        COUNTRY_ALIASES,
        INDEX_PATH,
        LEVEL_ALIASES,
        STRATEGY_ALIASES,
        build_index,
        tokenize,
    )
except ImportError:  # Allows direct script execution.
    from vector_store import (  # type: ignore
        COUNTRY_ALIASES,
        INDEX_PATH,
        LEVEL_ALIASES,
        STRATEGY_ALIASES,
        build_index,
        tokenize,
    )


GPA_RE = re.compile(r"(?:gpa|绩点|均分)?\s*(\d(?:\.\d+)?)", re.IGNORECASE)
WORK_YEAR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:年|years?|yrs?)", re.IGNORECASE)
WORK_MONTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个月|月|months?|mos?)", re.IGNORECASE)


@dataclass
class RetrievalResult:
    score: float
    case: dict[str, Any]
    reasons: list[str]

    @property
    def metadata(self) -> dict[str, Any]:
        return self.case["metadata"]

    @property
    def text(self) -> str:
        return self.case["text"]


def _normalize_country(value: str) -> str | None:
    lowered = value.lower()
    for alias, country in COUNTRY_ALIASES.items():
        if alias.lower() in lowered:
            return country
    return None


def _normalize_level(value: str) -> str | None:
    lowered = value.lower()
    for alias, level in LEVEL_ALIASES.items():
        if alias.lower() in lowered:
            return level
    return None


def _detect_strategy_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    for tag, aliases in STRATEGY_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            tags.append(tag)
    return sorted(set(tags))


def _extract_gpa(text: str) -> float | None:
    lowered = text.lower()
    if not any(marker in lowered for marker in ["gpa", "绩点", "均分"]):
        return None
    matches = [float(match.group(1)) for match in GPA_RE.finditer(text)]
    plausible = [value for value in matches if 0 < value <= 4.3]
    return plausible[0] if plausible else None


def _extract_work_years(text: str) -> float | None:
    years = [float(match.group(1)) for match in WORK_YEAR_RE.finditer(text)]
    if years:
        return max(years)
    months = [float(match.group(1)) for match in WORK_MONTH_RE.finditer(text)]
    if months:
        return round(max(months) / 12, 2)
    return None


def _wants_full_time_work(text: str) -> bool:
    lowered = text.lower()
    full_time_markers = ["工作经验", "工作", "全职", "毕业后", "从业", "职业", "公司", "industry", "work"]
    internship_markers = ["实习", "internship", "intern"]
    return any(marker in lowered for marker in full_time_markers) and not (
        any(marker in lowered for marker in internship_markers)
        and not any(marker in lowered for marker in ["工作", "全职", "毕业后", "work"])
    )


def _wants_product_experience(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ["产品", "产品经理", "product", "pm", "0到1", "上线", "用户"])


def _wants_ai_experience(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ["ai", "人工智能", "机器学习", "深度学习", "数据", "推荐系统"])


def _gpa_similarity(query_gpa: float | None, case_gpa: float | None) -> float:
    if query_gpa is None or case_gpa is None:
        return 0.0
    diff = abs(query_gpa - case_gpa)
    if diff <= 0.08:
        return 1.0
    if diff <= 0.18:
        return 0.75
    if diff <= 0.35:
        return 0.45
    if diff <= 0.55:
        return 0.2
    return -0.15


def _infer_query(query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    country = filters.get("country") or _normalize_country(query)
    level = filters.get("level") or _normalize_level(query)
    major = filters.get("major")
    if not major and any(term.lower() in query.lower() for term in ["cs", "computer", "计算机", "数据", "ai", "人工智能"]):
        major = "Computer Science"
    return {
        "country": country,
        "level": level,
        "major": major,
        "gpa": filters.get("gpa") if filters.get("gpa") is not None else _extract_gpa(query),
        "strategy_tags": filters.get("strategy_tags") or _detect_strategy_tags(query),
        "work_years": filters.get("work_years") if filters.get("work_years") is not None else _extract_work_years(query),
        "wants_full_time_work": filters.get("wants_full_time_work")
        if filters.get("wants_full_time_work") is not None
        else _wants_full_time_work(query),
        "wants_product_experience": filters.get("wants_product_experience")
        if filters.get("wants_product_experience") is not None
        else _wants_product_experience(query),
        "wants_ai_experience": filters.get("wants_ai_experience")
        if filters.get("wants_ai_experience") is not None
        else _wants_ai_experience(query),
    }


class HybridCaseRetriever:
    """Local hybrid retriever: metadata -> BM25 -> graph expansion -> rerank."""

    def __init__(self, index_path: Path = INDEX_PATH, rebuild: bool = False):
        if rebuild or not index_path.exists():
            build_index(index_path=index_path)
        self.index_path = index_path
        self.index = json.loads(index_path.read_text(encoding="utf-8"))
        self.documents = self.index["documents"]
        self.id_to_doc = {doc["id"]: doc for doc in self.documents}
        self.idf = self.index["stats"]["idf"]
        self.avgdl = self.index["stats"]["average_length"] or 1
        self.graph = self.index.get("graph", {})

    def _metadata_match(self, doc: dict[str, Any], inferred: dict[str, Any], strict: bool) -> tuple[bool, float, list[str]]:
        meta = doc["metadata"]
        score = 0.0
        reasons = []

        country = inferred.get("country")
        if country:
            countries = set(meta.get("target_countries") or [])
            countries.add(meta.get("country"))
            if country in countries:
                score += 2.5
                reasons.append(f"国家/地区匹配: {country}")
            elif strict:
                return False, score, reasons
            else:
                score -= 1.2

        level = inferred.get("level")
        if level:
            if meta.get("level") == level:
                score += 2.2
                reasons.append(f"申请阶段匹配: {level}")
            elif strict:
                return False, score, reasons
            else:
                score -= 1.0

        major = inferred.get("major")
        if major and meta.get("major"):
            if major.lower() in str(meta.get("major")).lower() or str(meta.get("major")).lower() in major.lower():
                score += 1.0
                reasons.append(f"专业匹配: {meta.get('major')}")

        gpa_score = _gpa_similarity(inferred.get("gpa"), meta.get("gpa"))
        if gpa_score:
            score += gpa_score
            reasons.append(f"GPA相近: 案例 {meta.get('gpa')}")

        query_work_years = inferred.get("work_years")
        case_work_years = meta.get("work_years")
        if query_work_years is not None:
            if case_work_years is not None:
                diff = abs(float(query_work_years) - float(case_work_years))
                if diff <= 0.25:
                    score += 2.7
                    reasons.append(f"工作年限高度匹配: 案例 {case_work_years}年")
                elif diff <= 0.75:
                    score += 1.8
                    reasons.append(f"工作年限接近: 案例 {case_work_years}年")
                elif diff <= 1.5:
                    score += 0.8
                    reasons.append(f"有相近工作年限: 案例 {case_work_years}年")
                elif float(case_work_years) < float(query_work_years):
                    score -= 0.6
            elif inferred.get("wants_full_time_work"):
                score -= 0.5

            if float(query_work_years) >= 1:
                if meta.get("has_full_time_work"):
                    score += 1.6
                    reasons.append("全职工作背景匹配")
                elif meta.get("has_internship_only"):
                    score -= 2.2
                    reasons.append("仅实习经历，低于用户工作年限")
        elif inferred.get("wants_full_time_work"):
            if meta.get("has_full_time_work"):
                score += 1.1
                reasons.append("有全职工作背景")
            elif meta.get("has_internship_only"):
                score -= 1.2
                reasons.append("用户偏工作背景，案例主要是实习")

        if inferred.get("wants_product_experience"):
            if meta.get("has_product_experience"):
                score += 1.5
                reasons.append("产品/上线经历匹配")
            else:
                score -= 0.25

        if inferred.get("wants_ai_experience"):
            if meta.get("has_ai_experience"):
                score += 0.85
                reasons.append("AI/数据经历匹配")

        query_tags = set(inferred.get("strategy_tags") or [])
        case_tags = set(meta.get("strategy_tags") or [])
        shared_tags = sorted(query_tags & case_tags)
        if shared_tags:
            score += 1.25 * len(shared_tags)
            reasons.append("策略信号匹配: " + ", ".join(shared_tags))

        return True, score, reasons

    def _bm25_score(self, query_tokens: list[str], doc: dict[str, Any]) -> float:
        counts = doc.get("token_counts") or {}
        doc_len = doc.get("length") or 1
        k1 = 1.45
        b = 0.72
        score = 0.0
        for token in query_tokens:
            tf = counts.get(token, 0)
            if not tf:
                continue
            idf = self.idf.get(token, 0.0)
            denom = tf + k1 * (1 - b + b * doc_len / self.avgdl)
            score += idf * (tf * (k1 + 1) / denom)
        return score

    def retrieve(
        self,
        query: str,
        k: int = 5,
        filters: dict[str, Any] | None = None,
        strict_metadata: bool = True,
        candidate_k: int = 18,
    ) -> list[RetrievalResult]:
        inferred = _infer_query(query, filters)
        query_tokens = tokenize(query + " " + " ".join(inferred.get("strategy_tags") or []))

        scored: list[tuple[str, float, list[str]]] = []
        fallback: list[tuple[str, float, list[str]]] = []
        for doc in self.documents:
            ok, meta_score, reasons = self._metadata_match(doc, inferred, strict=strict_metadata)
            bm25 = self._bm25_score(query_tokens, doc)
            combined = bm25 + meta_score
            if ok:
                scored.append((doc["id"], combined, reasons + ([f"BM25={bm25:.2f}"] if bm25 else [])))
            else:
                fallback.append((doc["id"], bm25 + meta_score, reasons + ([f"BM25={bm25:.2f}"] if bm25 else [])))

        if not scored and strict_metadata:
            scored = fallback

        scored.sort(key=lambda item: item[1], reverse=True)
        candidates = scored[:candidate_k]

        expanded = self._expand_with_graph(candidates, inferred)
        reranked = self._rerank(expanded, inferred, query_tokens)

        deduped = []
        seen_profiles = set()
        for case_id, score, reasons in reranked:
            doc = self.id_to_doc[case_id]
            profile_key = doc["metadata"].get("profile_id") or case_id
            if profile_key in seen_profiles:
                continue
            seen_profiles.add(profile_key)
            deduped.append(RetrievalResult(score=score, case=doc, reasons=reasons))
            if len(deduped) >= k:
                break

        return deduped

    def _expand_with_graph(
        self,
        candidates: list[tuple[str, float, list[str]]],
        inferred: dict[str, Any],
    ) -> list[tuple[str, float, list[str]]]:
        score_map: dict[str, float] = {}
        reason_map: dict[str, list[str]] = defaultdict(list)

        for case_id, score, reasons in candidates:
            score_map[case_id] = max(score_map.get(case_id, -999), score)
            reason_map[case_id].extend(reasons)
            for neighbor in self.graph.get("neighbors", {}).get(case_id, [])[:8]:
                if neighbor not in self.id_to_doc:
                    continue
                doc = self.id_to_doc[neighbor]
                has_hard_filter = bool(inferred.get("country") or inferred.get("level"))
                ok, meta_score, meta_reasons = self._metadata_match(
                    doc,
                    inferred,
                    strict=has_hard_filter,
                )
                if not ok:
                    continue
                graph_score = score * 0.18 + meta_score * 0.55
                if graph_score > score_map.get(neighbor, -999):
                    score_map[neighbor] = graph_score
                    reason_map[neighbor].extend(["图谱邻居扩展"] + meta_reasons)

        return [(case_id, score, reason_map[case_id]) for case_id, score in score_map.items()]

    def _rerank(
        self,
        candidates: list[tuple[str, float, list[str]]],
        inferred: dict[str, Any],
        query_tokens: list[str],
    ) -> list[tuple[str, float, list[str]]]:
        reranked = []
        query_token_set = set(query_tokens)
        for case_id, score, reasons in candidates:
            doc = self.id_to_doc[case_id]
            meta = doc["metadata"]
            counts = doc.get("token_counts") or {}
            coverage = len(query_token_set & set(counts.keys())) / max(len(query_token_set), 1)
            final_score = score + coverage * 2.0
            final_reasons = list(dict.fromkeys(reasons))

            if meta.get("scholarship_obtained"):
                final_score += 0.15

            if inferred.get("country") and inferred["country"] == meta.get("country"):
                final_score += 0.35
            if inferred.get("level") and inferred["level"] == meta.get("level"):
                final_score += 0.35

            if coverage:
                final_reasons.append(f"关键词覆盖={coverage:.2f}")

            reranked.append((case_id, final_score, final_reasons))

        reranked.sort(key=lambda item: item[1], reverse=True)
        return reranked

    def format_result(self, result: RetrievalResult, max_chars: int = 700) -> str:
        meta = result.metadata
        raw = result.case.get("raw_profile", {})
        lines = [
            f"{meta.get('name')} | {meta.get('country')} {meta.get('level')} | {meta.get('major')}",
            f"GPA/成绩: {meta.get('gpa') or '见原始案例'} | 最终选择: {meta.get('final_choice')}",
            "录取: " + "；".join(meta.get("admitted_schools") or []),
            "核心策略: " + "；".join(raw.get("key_strategies") or []),
            "经验: " + str(raw.get("lessons") or ""),
            "匹配原因: " + "；".join(result.reasons[:5]),
        ]
        text = "\n".join(line for line in lines if line.strip())
        return text[:max_chars]


def hybrid_retrieve(query: str, k: int = 5, **kwargs: Any) -> list[RetrievalResult]:
    return HybridCaseRetriever().retrieve(query, k=k, **kwargs)


def build_rag_context(query: str, k: int = 4, **kwargs: Any) -> dict[str, Any]:
    """Return retrieved cases in an LLM-friendly context package."""
    retriever = HybridCaseRetriever()
    results = retriever.retrieve(query, k=k, **kwargs)
    return {
        "query": query,
        "cases": [
            {
                "rank": rank,
                "score": round(result.score, 4),
                "metadata": result.metadata,
                "summary": retriever.format_result(result, max_chars=900),
                "raw_profile": result.case.get("raw_profile"),
                "reasons": result.reasons,
            }
            for rank, result in enumerate(results, 1)
        ],
        "prompt_context": "\n\n".join(
            f"[Case {rank}]\n{retriever.format_result(result, max_chars=900)}"
            for rank, result in enumerate(results, 1)
        ),
    }


if __name__ == "__main__":
    retriever = HybridCaseRetriever(rebuild=False)
    tests = [
        ("GPA 3.6，有信息学奥赛和ACM比赛，想申请美国CS本科", {"level": "undergrad", "country": "US"}),
        ("985本科，GPA 3.7，有科研经历，想申请加拿大CS研究型硕士", {"level": "graduate", "country": "Canada"}),
        ("本科背景一般但有2年AI产品工作经验，想申请美国CS硕士", {"level": "graduate", "country": "US"}),
    ]
    for query, filters in tests:
        print("\n" + "=" * 88)
        print(query)
        for i, item in enumerate(retriever.retrieve(query, filters=filters, k=3), 1):
            print(f"\nTop {i} score={item.score:.2f}")
            print(retriever.format_result(item, max_chars=500))
