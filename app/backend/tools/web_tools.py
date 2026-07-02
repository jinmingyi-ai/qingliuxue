# -*- coding: utf-8 -*-
"""Web-research tool abstractions for specialist agents.

Network access is intentionally optional.  In production this module can be
connected to Tavily/SerpAPI/Bing/official-site crawlers.  For local tests it
returns a structured research plan and stable source hints, so agents can still
produce grounded answers without pretending to have live search results.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # Keep local smoke tests usable without optional packages.
    def load_dotenv(*_: Any, **__: Any) -> bool:
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


OFFICIAL_SOURCE_HINTS = {
    "US": {
        "case": ["大学项目官网 admissions/requirements", "项目 curriculum 页面", "学校 career outcomes 页面"],
        "timeline": ["Common App", "大学项目官网 admissions/deadlines", "ETS/IELTS 官网"],
        "materials": ["Common App", "各大学 Graduate Admissions", "学校 Registrar/WES 要求"],
        "visa": ["travel.state.gov", "studyinthestates.dhs.gov", "uscis.gov"],
        "career": ["学校 career outcomes 页面", "USCIS OPT/STEM OPT 官方说明"],
    },
    "UK": {
        "case": ["大学 course pages", "大学 admissions pages", "Discover Uni/大学 employability 页面"],
        "timeline": ["UCAS", "大学 course pages", "UKCISA"],
        "materials": ["UCAS", "大学 admissions pages"],
        "visa": ["gov.uk Student visa", "UKCISA"],
        "career": ["gov.uk Graduate visa", "大学 employability/careers 页面"],
    },
    "Canada": {
        "case": ["大学 program pages", "大学 admissions/deadlines", "大学 co-op/career outcomes 页面"],
        "timeline": ["各大学 admissions/deadlines", "IRCC study permit"],
        "materials": ["大学 admissions pages", "WES Canada 如项目要求"],
        "visa": ["IRCC study permit", "IRCC PGWP"],
        "career": ["IRCC PGWP", "省提名/移民项目官方页"],
    },
    "Australia": {
        "case": ["大学 international admissions", "课程 handbook/program pages", "大学 graduate outcomes 页面"],
        "timeline": ["大学 international admissions", "UAC/VTAC/QTAC 如适用"],
        "materials": ["大学 admissions pages", "澳洲学历/英语要求页面"],
        "visa": ["immi.homeaffairs.gov.au Student visa subclass 500"],
        "career": ["Temporary Graduate visa subclass 485", "大学 career outcomes"],
    },
}


@dataclass
class WebResearchResult:
    topic: str
    query: str
    country: str | None
    level: str | None
    status: str
    source_hints: list[str]
    verification_tasks: list[str]
    notes: list[str]
    generated_at: str
    provider: str | None = None
    search_query: str | None = None
    answer: str | None = None
    results: list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebResearchTool:
    """Create structured web-research tasks and source hints."""

    def research(
        self,
        topic: str,
        query: str,
        country: str | None = None,
        level: str | None = None,
        program: str | None = None,
    ) -> WebResearchResult:
        source_hints = self._source_hints(topic=topic, country=country)
        verification_tasks = self._verification_tasks(topic, query, country, level, program)
        search_query = self._search_query(topic, query, country, level, program, source_hints)
        live = self._tavily_search(search_query, country=country)
        notes = []
        if live and live.get("ok"):
            notes.append("已通过 Tavily 执行实时网页搜索；最终回答仍应优先引用官方来源。")
            status = "live_search"
            provider = "tavily"
            answer = live.get("answer")
            results = live.get("results") or []
            usage = live.get("usage")
            error = None
        else:
            notes.append("本地环境未接入 Tavily 或搜索失败时，此结果作为检索计划和官方来源提示使用。")
            status = "research_plan" if not live else "search_error"
            provider = "tavily" if live else None
            answer = None
            results = []
            usage = None
            error = live.get("error") if live else None
        notes.append("动态信息如截止日期、签证费用、项目要求应以官方网页最新内容为准。")
        return WebResearchResult(
            topic=topic,
            query=query,
            country=country,
            level=level,
            status=status,
            source_hints=source_hints,
            verification_tasks=verification_tasks,
            notes=notes,
            generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            provider=provider,
            search_query=search_query,
            answer=answer,
            results=results,
            usage=usage,
            error=error,
        )

    def _source_hints(self, topic: str, country: str | None) -> list[str]:
        if country and country in OFFICIAL_SOURCE_HINTS:
            country_sources = OFFICIAL_SOURCE_HINTS[country]
            if topic in country_sources:
                return country_sources[topic]
            return sorted({source for sources in country_sources.values() for source in sources})
        return [
            "目标学校/项目官网 admissions 或 requirements 页面",
            "目标国家移民局/签证中心官网",
            "官方考试机构页面",
        ]

    def _verification_tasks(
        self,
        topic: str,
        query: str,
        country: str | None,
        level: str | None,
        program: str | None,
    ) -> list[str]:
        base = []
        if country:
            base.append(f"确认 {country} 方向与用户问题相关的官方政策或院校要求。")
        if level:
            base.append(f"区分 {level} 阶段的申请时间线、材料或签证差异。")
        if program:
            base.append(f"核对 {program} 项目的最新截止日期、材料清单和语言要求。")

        topic_tasks = {
            "timeline": [
                "核对目标项目最近一个申请季的开放日期、主轮次截止日期、奖学金截止日期。",
                "核对语言/标化考试送分和推荐信提交的实际截止要求。",
            ],
            "case": [
                "检索与用户背景相近的目标项目官网，核对录取要求、课程设置、申请轮次和就业数据。",
                "用官方项目页补齐私有案例库不足的部分，不把小样本案例误当作确定结论。",
            ],
            "comparison": [
                "核对每个方案的项目长度、学费、课程设置、就业数据和申请要求。",
                "优先引用项目官网和官方 career outcomes 页面。",
            ],
            "materials": [
                "核对成绩单、推荐信、简历、文书、资金证明、作品集等是否为必需项。",
                "确认是否需要 WES/认证/公证/学校邮箱推荐信等特殊要求。",
            ],
            "visa": [
                "核对签证类型、资金证明、体检/保险、审理周期和毕业后工作签证政策。",
                "动态政策只引用移民局或政府官网。",
            ],
        }
        base.extend(topic_tasks.get(topic, ["核对官方来源并记录更新时间。"]))
        if query:
            base.append(f"围绕用户原问题检索: {query}")
        return base

    def _search_query(
        self,
        topic: str,
        query: str,
        country: str | None,
        level: str | None,
        program: str | None,
        source_hints: list[str],
    ) -> str:
        country_part = country or ""
        level_part = level or ""
        program_part = program or ""
        topic_terms = {
            "case": "official admissions requirements curriculum career outcomes similar programs",
            "timeline": "official admissions deadlines application timeline scholarship deadline",
            "comparison": "official tuition curriculum admissions requirements career outcomes",
            "materials": "official application requirements documents transcript recommendation statement",
            "visa": "official student visa requirements government immigration",
            "career": "official post study work visa career outcomes employment report",
        }.get(topic, "official admissions requirements")
        return " ".join(
            part
            for part in [
                query,
                country_part,
                level_part,
                program_part,
                topic_terms,
                " ".join(source_hints[:3]),
            ]
            if part
        )

    def _tavily_search(self, search_query: str, country: str | None = None) -> dict[str, Any] | None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return None

        payload: dict[str, Any] = {
            "query": search_query,
            "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
            "max_results": int(os.getenv("TAVILY_MAX_RESULTS", "5")),
            "include_answer": "basic",
            "include_raw_content": False,
            "include_favicon": True,
            "include_usage": True,
        }
        tavily_country = self._tavily_country(country)
        if tavily_country:
            payload["country"] = tavily_country

        try:
            response = requests.post(
                TAVILY_SEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15")),
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "answer": data.get("answer"),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                    "favicon": item.get("favicon"),
                }
                for item in data.get("results", [])[: int(os.getenv("TAVILY_MAX_RESULTS", "5"))]
            ],
            "usage": data.get("usage"),
            "request_id": data.get("request_id"),
            "response_time": data.get("response_time"),
        }

    def _tavily_country(self, country: str | None) -> str | None:
        return {
            "US": "united states",
            "UK": "united kingdom",
            "Canada": "canada",
            "Australia": "australia",
            "Singapore": "singapore",
            "Hong Kong": "china",
        }.get(country or "")


def web_research(
    topic: str,
    query: str,
    country: str | None = None,
    level: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    return WebResearchTool().research(topic, query, country, level, program).to_dict()
