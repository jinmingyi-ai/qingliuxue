# -*- coding: utf-8 -*-
"""Web-research tool abstractions for specialist agents.

Network access is intentionally optional.  In production this module can be
connected to Tavily/SerpAPI/Bing/official-site crawlers.  For local tests it
returns a structured research plan and stable source hints, so agents can still
produce grounded answers without pretending to have live search results.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


OFFICIAL_SOURCE_HINTS = {
    "US": {
        "timeline": ["Common App", "大学项目官网 admissions/deadlines", "ETS/IELTS 官网"],
        "materials": ["Common App", "各大学 Graduate Admissions", "学校 Registrar/WES 要求"],
        "visa": ["travel.state.gov", "studyinthestates.dhs.gov", "uscis.gov"],
        "career": ["学校 career outcomes 页面", "USCIS OPT/STEM OPT 官方说明"],
    },
    "UK": {
        "timeline": ["UCAS", "大学 course pages", "UKCISA"],
        "materials": ["UCAS", "大学 admissions pages"],
        "visa": ["gov.uk Student visa", "UKCISA"],
        "career": ["gov.uk Graduate visa", "大学 employability/careers 页面"],
    },
    "Canada": {
        "timeline": ["各大学 admissions/deadlines", "IRCC study permit"],
        "materials": ["大学 admissions pages", "WES Canada 如项目要求"],
        "visa": ["IRCC study permit", "IRCC PGWP"],
        "career": ["IRCC PGWP", "省提名/移民项目官方页"],
    },
    "Australia": {
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
        notes = [
            "本地环境未接入实时搜索 API 时，此结果作为检索计划和官方来源提示使用。",
            "真正生成最终建议前，动态信息如截止日期、签证费用、项目要求应以官方网页最新内容为准。",
        ]
        return WebResearchResult(
            topic=topic,
            query=query,
            country=country,
            level=level,
            status="research_plan",
            source_hints=source_hints,
            verification_tasks=verification_tasks,
            notes=notes,
            generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
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


def web_research(
    topic: str,
    query: str,
    country: str | None = None,
    level: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    return WebResearchTool().research(topic, query, country, level, program).to_dict()
