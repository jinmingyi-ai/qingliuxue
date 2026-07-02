# -*- coding: utf-8 -*-
"""Tiny HTTP client used by the Streamlit frontend."""

from __future__ import annotations

import os
from typing import Any

import requests


class ApiClientError(RuntimeError):
    """Raised when the backend API cannot complete a request."""


def api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, path: str, token: str | None = None, **kwargs: Any) -> dict[str, Any]:
    url = api_base_url() + path
    try:
        response = requests.request(method, url, headers=_headers(token), timeout=45, **kwargs)
    except requests.RequestException as exc:
        raise ApiClientError(f"后端服务暂时不可用：{exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("error") or str(detail)
        raise ApiClientError(str(detail))
    try:
        return response.json()
    except ValueError as exc:
        raise ApiClientError("后端返回了无法解析的数据") from exc


def register_user(email: str, password: str) -> dict[str, Any]:
    return _request(
        "POST",
        "/auth/register",
        json={"email": email, "password": password},
    )


def login_user(email: str, password: str) -> dict[str, Any]:
    return _request("POST", "/auth/login", json={"email": email, "password": password})


def get_me(token: str) -> dict[str, Any]:
    return _request("GET", "/auth/me", token=token)


def chat_message(
    message: str,
    token: str | None = None,
    conversation_id: str | None = None,
    entry: str = "chat",
    requested_agents: list[str] | None = None,
    questionnaire: dict[str, Any] | None = None,
    guest_session_id: str | None = None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/chat",
        token=token,
        json={
            "message": message,
            "conversation_id": conversation_id,
            "entry": entry,
            "requested_agents": requested_agents,
            "questionnaire": questionnaire,
            "guest_session_id": guest_session_id,
        },
    )


def create_conversation(
    token: str | None = None,
    title: str | None = None,
    entry_point: str = "chat",
    guest_session_id: str | None = None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/conversations",
        token=token,
        json={"title": title, "entry_point": entry_point, "guest_session_id": guest_session_id},
    )


def list_conversations(token: str | None = None, guest_session_id: str | None = None) -> dict[str, Any]:
    params = {"guest_session_id": guest_session_id} if guest_session_id else None
    return _request("GET", "/conversations", token=token, params=params)


def submit_questionnaire(
    questionnaire: dict[str, Any],
    token: str | None = None,
    conversation_id: str | None = None,
    guest_session_id: str | None = None,
) -> dict[str, Any]:
    return _request(
        "POST",
        "/questionnaire",
        token=token,
        json={
            "questionnaire": questionnaire,
            "conversation_id": conversation_id,
            "guest_session_id": guest_session_id,
        },
    )
