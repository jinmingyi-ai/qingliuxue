# -*- coding: utf-8 -*-
"""Pydantic request/response schemas for the FastAPI layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuthRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    entry: str = "chat"
    requested_agents: list[str] | None = None
    questionnaire: dict[str, Any] | None = None
    guest_session_id: str | None = None


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    entry_point: str = "chat"
    guest_session_id: str | None = None


class QuestionnaireRequest(BaseModel):
    questionnaire: dict[str, Any]
    conversation_id: str | None = None
    guest_session_id: str | None = None

