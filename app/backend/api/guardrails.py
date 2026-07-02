# -*- coding: utf-8 -*-
"""Security guardrails for public API traffic and LLM-facing chat flows."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


MAX_MESSAGE_CHARS = 4000
MAX_QUESTIONNAIRE_CHARS = 20000
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 90

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

SENSITIVE_KEYS = {
    "memory_prompt_context",
    "raw",
    "raw_profile",
    "prompt",
    "system_prompt",
    "system_instruction",
    "api_key",
    "password_hash",
    "token",
    "authorization",
    "search_query",
    "content",
}

INJECTION_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"ignore (all )?(previous|prior|above) instructions",
        r"disregard (all )?(previous|prior|above) instructions",
        r"reveal (your )?(system|developer) (prompt|message|instruction)",
        r"show (your )?(system|developer) (prompt|message|instruction)",
        r"dump .*?(rag|database|memory|vector|prompt|source code)",
        r"print .*?(rag|database|memory|vector|prompt|source code)",
        r"泄露.*?(系统|提示词|prompt|rag|知识库|数据库|源码|密钥|token)",
        r"导出.*?(系统|提示词|prompt|rag|知识库|数据库|源码|密钥|token)",
        r"忽略.*?(之前|以上|系统).*?(指令|规则)",
        r"显示.*?(系统|开发者).*?(提示词|指令)",
        r"把.*?(系统提示词|知识库|数据库|源码|密钥|token).*?(发给我|给我|输出)",
    ]
]

SECRET_PATTERNS = [
    re.compile(r"xai-[A-Za-z0-9_-]{20,}", re.I),
    re.compile(r"hf_[A-Za-z0-9]{20,}", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.I),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]


class SecurityHeadersAndRateLimitMiddleware(BaseHTTPMiddleware):
    """Attach security headers and apply a compact in-memory rate limit."""

    def __init__(self, app: Any, max_requests: int = RATE_LIMIT_MAX_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        key = self._rate_limit_key(request)
        now = time.monotonic()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            response: Response = JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
        else:
            bucket.append(now)
            response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    def _rate_limit_key(self, request: Request) -> str:
        auth = request.headers.get("authorization")
        if auth:
            return "auth:" + auth[-24:]
        client_host = request.client.host if request.client else "unknown"
        return "ip:" + client_host


def inspect_chat_input(message: str, questionnaire: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and classify inbound chat/questionnaire content."""
    message = message or ""
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"消息过长，请控制在 {MAX_MESSAGE_CHARS} 字以内")
    if questionnaire is not None:
        serialized = json.dumps(questionnaire, ensure_ascii=False)
        if len(serialized) > MAX_QUESTIONNAIRE_CHARS:
            raise HTTPException(status_code=413, detail="问卷内容过长，请缩短补充说明后再提交")

    injection_hits = [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(message)]
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(message)]
    return {
        "blocked": bool(injection_hits or secret_hits),
        "injection_hits": injection_hits,
        "secret_hits": secret_hits,
    }


def blocked_chat_response(query: str, conversation_id: str | None, profile: dict[str, Any]) -> dict[str, Any]:
    """Return a safe assistant answer without invoking downstream agents."""
    return {
        "supervisor": "study_abroad_supervisor",
        "query": query,
        "conversation_id": conversation_id,
        "route": [],
        "answer": (
            "这个请求涉及内部规则、内部知识、密钥或站点结构，我不能提供这些内容。"
            "如果你是想做留学规划，我可以继续帮你分析选校、时间线、材料、签证或就业路径。"
        ),
        "answer_source": "security_harness",
        "agent_results": [],
        "profile": profile,
        "confidence": 1.0,
        "diagnostics": {"blocked_by_security_harness": True},
    }


def sanitize_api_result(result: dict[str, Any]) -> dict[str, Any]:
    """Strip internal prompt/RAG/search details before returning JSON to clients."""
    public = deepcopy(result)
    public["agent_results"] = [_sanitize_agent_result(item) for item in public.get("agent_results") or []]
    diagnostics = public.get("diagnostics") or {}
    public["diagnostics"] = {
        "official_check_needed": diagnostics.get("web_search_needed"),
        "official_check_enabled": diagnostics.get("web_search_enabled"),
        "blocked_by_security_harness": diagnostics.get("blocked_by_security_harness", False),
    }
    public["answer"] = sanitize_text(str(public.get("answer") or ""))
    return public


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[已隐藏敏感信息]", sanitized)
    sanitized = re.sub(r"(?i)\b(system|developer) prompt\b", "内部规则", sanitized)
    sanitized = re.sub(r"(?i)\bRAG\b", "参考信息", sanitized)
    sanitized = sanitized.replace("私有案例库", "真实案例").replace("联网核对", "官方核对")
    return sanitized


def _sanitize_agent_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": result.get("agent"),
        "task": result.get("task"),
        "answer": sanitize_text(str(result.get("answer") or "")),
        "structured": _public_structured(result.get("structured") or {}),
        "sources": _public_sources(result.get("sources") or []),
        "confidence": result.get("confidence"),
    }


def _public_structured(value: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, item in value.items():
        if key in SENSITIVE_KEYS:
            continue
        if key == "web_research":
            continue
        if key in {"goal", "recommended_routes", "timeline", "essay_strategy", "comparison_matrix", "recommendation", "material_checklist", "visa_and_career_plan", "missing_fields", "profile"}:
            public[key] = _redact_nested(item)
        elif key == "rag_support":
            public["reference_support"] = item
        elif key.endswith("_count") or key in {"document_type"}:
            public[key] = item
    return public


def _summarize_web_research(value: Any) -> Any:
    if isinstance(value, list):
        return [_summarize_web_research(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        "topic": value.get("topic"),
        "status": value.get("status"),
        "provider": value.get("provider"),
        "result_count": len(value.get("results") or []),
        "source_hints": value.get("source_hints") or [],
    }


def _public_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_sources = []
    for source in sources[:8]:
        public_sources.append(
            {
                "type": "reference",
                "topic": source.get("topic"),
                "result_count": len(source.get("results") or []),
                "results": [
                    {"title": item.get("title"), "url": item.get("url")}
                    for item in (source.get("results") or [])[:3]
                ],
            }
        )
    return public_sources


def _redact_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_nested(item) for key, item in value.items() if key not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [_redact_nested(item) for item in value[:20]]
    if isinstance(value, str):
        return sanitize_text(value)
    return value
