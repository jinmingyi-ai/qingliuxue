# -*- coding: utf-8 -*-
"""Specialist agents for the study-abroad advisor graph."""

from app.backend.agents.specialists.case_recommendation_agent import CaseRecommendationAgent
from app.backend.agents.specialists.comparison_agent import ComparisonAgent
from app.backend.agents.specialists.essay_agent import EssayAgent
from app.backend.agents.specialists.material_agent import MaterialAgent
from app.backend.agents.specialists.profile_agent import ProfileAgent
from app.backend.agents.specialists.timeline_agent import TimelineAgent
from app.backend.agents.specialists.visa_career_agent import VisaCareerAgent

__all__ = [
    "CaseRecommendationAgent",
    "ComparisonAgent",
    "EssayAgent",
    "MaterialAgent",
    "ProfileAgent",
    "TimelineAgent",
    "VisaCareerAgent",
]
