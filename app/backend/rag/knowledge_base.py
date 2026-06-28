# -*- coding: utf-8 -*-
"""Hybrid RAG for small structured knowledge bases.

This module indexes the private JSON knowledge files used by specialist agents:

- files.json: essay / document strategy knowledge
- prepare.json: application material preparation knowledge

The index is local and deterministic.  It combines metadata matching with
BM25-style sparse retrieval, which is a good fit for compact structured JSON
where country, level, and document type matter more than generic similarity.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROFILE_DIR = BASE_DIR / "app" / "data" / "profiles"
INDEX_DIR = BASE_DIR / "app" / "data" / "rag_index"

DATASETS = {
    "essay": {
        "source": PROFILE_DIR / "files.json",
        "index": INDEX_DIR / "essay_index.json",
        "description": "文书策略与指导知识库",
    },
    "prepare": {
        "source": PROFILE_DIR / "prepare.json",
        "index": INDEX_DIR / "prepare_index.json",
        "description": "申请材料准备知识库",
    },
}

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{1,2}")

COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "america": "US",
    "美国": "US",
    "美研": "US",
    "美本": "US",
    "uk": "UK",
    "britain": "UK",
    "英国": "UK",
    "英研": "UK",
    "英本": "UK",
    "canada": "Canada",
    "加拿大": "Canada",
    "australia": "Australia",
    "澳洲": "Australia",
    "澳大利亚": "Australia",
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
    "硕申": "graduate",
}

DOCUMENT_ALIASES = {
    "sop": "Statement of Purpose",
    "statement of purpose": "Statement of Purpose",
    "ps": "Personal Statement",
    "personal statement": "Personal Statement",
    "文书": "Personal Statement",
    "个人陈述": "Personal Statement",
    "动机信": "Statement of Purpose",
    "statement of interest": "Statement of Interest",
    "soi": "Statement of Interest",
    "cv": "CV",
    "resume": "Resume",
    "简历": "Resume",
    "推荐信": "Recommendation Letter",
    "lor": "Recommendation Letter",
    "成绩单": "Transcript",
    "transcript": "Transcript",
    "portfolio": "Portfolio",
    "作品集": "Portfolio",
}

LABEL_HINTS = {
    "EssayRequirement": ["要求", "需要写什么", "核心", "区别", "requirement"],
    "EssayStructure": ["结构", "框架", "段落", "怎么组织", "structure"],
    "ChinaStudentEssayIssues": ["问题", "错误", "坑", "常见问题", "mistake"],
    "EssayStrategyByBackground": ["策略", "背景", "怎么突出", "写法", "strategy"],
    "MaterialPreparation": ["材料", "清单", "准备", "成绩单", "推荐信", "签证材料"],
}

FIELD_WEIGHTS = {
    "identity": 5,
    "metadata": 4,
    "content": 4,
    "strategies": 5,
    "issues": 5,
    "timeline": 4,
    "relationships": 2,
}


@dataclass
class KnowledgeResult:
    score: float
    document: dict[str, Any]
    reasons: list[str]

    @property
    def metadata(self) -> dict[str, Any]:
        return self.document["metadata"]

    @property
    def raw(self) -> dict[str, Any]:
        return self.document.get("raw", {})


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
        chunks = []
        for key, item in value.items():
            text = _flatten_text(item)
            if text:
                chunks.append(f"{key}: {text}")
        return "；".join(chunks)
    return str(value)


def tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = TOKEN_RE.findall(lowered)
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2}", token):
            expanded.extend(token)
    return expanded


def _weighted_tokens(fields: dict[str, str]) -> list[str]:
    tokens: list[str] = []
    for field, text in fields.items():
        field_tokens = tokenize(text)
        for _ in range(FIELD_WEIGHTS.get(field, 1)):
            tokens.extend(field_tokens)
    return tokens


def normalize_country(text: str | None) -> str | None:
    lowered = (text or "").lower()
    for alias, country in COUNTRY_ALIASES.items():
        if alias.lower() in lowered:
            return country
    return None


def normalize_level(text: str | None) -> str | None:
    lowered = (text or "").lower()
    for alias, level in LEVEL_ALIASES.items():
        if alias.lower() in lowered:
            return level
    return None


def normalize_document_type(text: str | None) -> str | None:
    lowered = (text or "").lower()
    for alias, document_type in DOCUMENT_ALIASES.items():
        if alias.lower() in lowered:
            return document_type
    return None


def _matches_document_type(query_type: str, candidate_types: list[str]) -> bool:
    lowered_query = query_type.lower()
    for candidate in candidate_types:
        lowered_candidate = candidate.lower()
        if lowered_query in lowered_candidate or lowered_candidate in lowered_query:
            return True
    return False


def _infer_label(query: str) -> str | None:
    lowered = query.lower()
    for label, hints in LABEL_HINTS.items():
        if any(hint.lower() in lowered for hint in hints):
            return label
    return None


def _extract_nodes(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for item_index, item in enumerate(data):
        relationships.extend(item.get("relationships", []))
        for node in item.get("nodes", []):
            properties = dict(node.get("properties") or {})
            properties["_node_id"] = node.get("id")
            properties["_label"] = node.get("label")
            properties["_item_index"] = item_index
            nodes.append(properties)
    return nodes, relationships


def _relationship_text(relationships: list[dict[str, Any]], node_id: str | None) -> str:
    if not node_id:
        return ""
    chunks = []
    for rel in relationships:
        if rel.get("start_node_id") == node_id or rel.get("end_node_id") == node_id:
            chunks.append(_flatten_text(rel))
    return "；".join(chunks)


def _node_to_document(node: dict[str, Any], relationships: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    node_id = node.get("_node_id")
    label = node.get("_label")
    country = node.get("country")
    levels = [str(item) for item in _as_list(node.get("level"))]
    document_types = [str(item) for item in _as_list(node.get("document_type"))]

    strategy_keys = [
        "effective_strategies_from_real_cases",
        "recommended_structure",
        "strategies",
        "strategy_by_background",
        "background_based_strategy",
        "key_tips",
    ]
    issue_keys = [
        "china_student_pain_points",
        "common_mistakes",
        "common_issues_for_chinese_students",
    ]
    timeline_keys = ["preparation_timeline", "timeline", "deadline_notes"]

    fields = {
        "identity": _flatten_text(
            {
                "id": node_id,
                "label": label,
                "dataset": dataset,
                "country": country,
                "level": levels,
                "document_type": document_types,
            }
        ),
        "metadata": _flatten_text(
            {
                "country": country,
                "level": levels,
                "document_type": document_types,
            }
        ),
        "content": _flatten_text({key: value for key, value in node.items() if not key.startswith("_")}),
        "strategies": _flatten_text({key: node.get(key) for key in strategy_keys if key in node}),
        "issues": _flatten_text({key: node.get(key) for key in issue_keys if key in node}),
        "timeline": _flatten_text({key: node.get(key) for key in timeline_keys if key in node}),
        "relationships": _relationship_text(relationships, node_id),
    }

    metadata = {
        "id": node_id,
        "label": label,
        "dataset": dataset,
        "country": country,
        "levels": levels,
        "document_types": document_types,
    }

    return {
        "id": f"{dataset}:{node_id}",
        "metadata": metadata,
        "fields": fields,
        "text": "\n".join(f"{key}: {value}" for key, value in fields.items() if value),
        "tokens": _weighted_tokens(fields),
        "raw": {key: value for key, value in node.items() if not key.startswith("_")},
    }


def build_knowledge_index(dataset: str, rebuild: bool = True) -> dict[str, Any]:
    if dataset not in DATASETS:
        raise ValueError(f"Unknown knowledge dataset: {dataset}")

    source_path = DATASETS[dataset]["source"]
    index_path = DATASETS[dataset]["index"]
    if index_path.exists() and not rebuild:
        return json.loads(index_path.read_text(encoding="utf-8"))

    data = json.loads(source_path.read_text(encoding="utf-8"))
    nodes, relationships = _extract_nodes(data)
    documents = [_node_to_document(node, relationships, dataset) for node in nodes]

    document_frequency: Counter[str] = Counter()
    lengths = []
    for doc in documents:
        counts = Counter(doc["tokens"])
        doc["token_counts"] = dict(counts)
        doc["length"] = sum(counts.values())
        lengths.append(doc["length"])
        document_frequency.update(counts.keys())
        doc.pop("tokens", None)

    average_length = sum(lengths) / max(len(lengths), 1)
    idf = {
        token: math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
        for token, df in document_frequency.items()
    }
    index = {
        "version": 1,
        "dataset": dataset,
        "description": DATASETS[dataset]["description"],
        "source": str(source_path),
        "documents": documents,
        "stats": {
            "document_count": len(documents),
            "average_length": average_length,
            "idf": idf,
        },
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def build_all_knowledge_indexes() -> dict[str, dict[str, Any]]:
    return {dataset: build_knowledge_index(dataset, rebuild=True) for dataset in DATASETS}


class KnowledgeBaseRetriever:
    """Retrieve from one structured private knowledge dataset."""

    def __init__(self, dataset: str, rebuild: bool = False):
        if dataset not in DATASETS:
            raise ValueError(f"Unknown knowledge dataset: {dataset}")
        self.dataset = dataset
        self.index_path = DATASETS[dataset]["index"]
        if rebuild or not self.index_path.exists():
            self.index = build_knowledge_index(dataset, rebuild=True)
        else:
            self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.documents = self.index["documents"]
        self.idf = self.index["stats"]["idf"]
        self.avgdl = self.index["stats"]["average_length"] or 1

    def retrieve(
        self,
        query: str,
        k: int = 4,
        filters: dict[str, Any] | None = None,
        strict_metadata: bool = True,
    ) -> list[KnowledgeResult]:
        inferred = self._infer(query, filters or {})
        query_tokens = tokenize(query + " " + _flatten_text(inferred))
        scored: list[KnowledgeResult] = []
        fallback: list[KnowledgeResult] = []

        for doc in self.documents:
            ok, meta_score, reasons = self._metadata_score(doc, inferred, strict_metadata)
            bm25 = self._bm25(query_tokens, doc)
            coverage = self._coverage(query_tokens, doc)
            label_score = self._label_score(doc, inferred)
            score = meta_score + bm25 + coverage * 1.5 + label_score
            all_reasons = reasons + ([f"BM25={bm25:.2f}"] if bm25 else []) + ([f"关键词覆盖={coverage:.2f}"] if coverage else [])
            result = KnowledgeResult(score=score, document=doc, reasons=all_reasons)
            if ok:
                scored.append(result)
            else:
                fallback.append(result)

        results = scored if scored else fallback
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:k]

    def _infer(self, query: str, filters: dict[str, Any]) -> dict[str, Any]:
        return {
            "country": filters.get("country") or normalize_country(query),
            "level": filters.get("level") or normalize_level(query),
            "document_type": filters.get("document_type") or normalize_document_type(query),
            "label": filters.get("label") or _infer_label(query),
        }

    def _metadata_score(self, doc: dict[str, Any], inferred: dict[str, Any], strict: bool) -> tuple[bool, float, list[str]]:
        meta = doc["metadata"]
        score = 0.0
        reasons: list[str] = []

        country = inferred.get("country")
        if country:
            if meta.get("country") == country:
                score += 3.0
                reasons.append(f"国家/地区匹配: {country}")
            elif strict:
                return False, score, reasons
            else:
                score -= 1.0

        level = inferred.get("level")
        if level:
            levels = meta.get("levels") or []
            if not levels or level in levels:
                score += 1.4
                reasons.append(f"申请阶段匹配: {level}")
            elif strict:
                return False, score, reasons

        document_type = inferred.get("document_type")
        if document_type:
            doc_types = meta.get("document_types") or []
            if not doc_types or _matches_document_type(document_type, doc_types):
                score += 1.8
                reasons.append(f"文档类型匹配: {document_type}")
            elif strict and self.dataset == "essay":
                return False, score, reasons

        return True, score, reasons

    def _label_score(self, doc: dict[str, Any], inferred: dict[str, Any]) -> float:
        label = inferred.get("label")
        if label and doc["metadata"].get("label") == label:
            return 1.25
        return 0.0

    def _bm25(self, query_tokens: list[str], doc: dict[str, Any]) -> float:
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

    def _coverage(self, query_tokens: list[str], doc: dict[str, Any]) -> float:
        token_set = set(query_tokens)
        if not token_set:
            return 0.0
        return len(token_set & set((doc.get("token_counts") or {}).keys())) / len(token_set)

    def format_result(self, result: KnowledgeResult, max_chars: int = 900) -> str:
        meta = result.metadata
        raw = result.raw
        title = " | ".join(
            str(part)
            for part in [
                meta.get("label"),
                meta.get("country"),
                ", ".join(meta.get("document_types") or []),
            ]
            if part
        )
        body = _flatten_text(raw)
        reasons = "；".join(result.reasons[:5])
        text = f"{title}\n内容: {body}\n匹配原因: {reasons}"
        return text[:max_chars]


def build_knowledge_context(
    dataset: str,
    query: str,
    k: int = 4,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retriever = KnowledgeBaseRetriever(dataset)
    results = retriever.retrieve(query, k=k, filters=filters)
    return {
        "dataset": dataset,
        "query": query,
        "results": [
            {
                "rank": rank,
                "score": round(result.score, 4),
                "metadata": result.metadata,
                "summary": retriever.format_result(result),
                "raw": result.raw,
                "reasons": result.reasons,
            }
            for rank, result in enumerate(results, 1)
        ],
        "prompt_context": "\n\n".join(
            f"[{dataset} Knowledge {rank}]\n{retriever.format_result(result)}"
            for rank, result in enumerate(results, 1)
        ),
    }


if __name__ == "__main__":
    indexes = build_all_knowledge_indexes()
    for name, index in indexes.items():
        print(f"{name}: {index['stats']['document_count']} documents -> {DATASETS[name]['index']}")
