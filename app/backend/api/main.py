# -*- coding: utf-8 -*-
"""FastAPI backend for Qingliuxue.

Run locally:
    uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.backend.agents.supervisor import StudyAbroadSupervisor
from app.backend.api import db
from app.backend.api.schemas import AuthRequest, AuthResponse, ChatRequest, ConversationCreateRequest, QuestionnaireRequest
from app.backend.api.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    validate_email,
    validate_password,
    verify_password,
)
from app.backend.memory.memory_manager import MemoryManager


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
MEMORY_ROOT = BASE_DIR / "app" / "data" / "memory"


app = FastAPI(title="轻留学 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()


def _token_from_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="认证格式应为 Bearer token")
    return token


def optional_user(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    token = _token_from_header(authorization)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get_user_by_id(str(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def required_user(user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def _safe_store_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _guest_id(guest_session_id: str | None) -> str:
    if guest_session_id and re.match(r"^[A-Za-z0-9_.-]{8,80}$", guest_session_id):
        return "guest_" + guest_session_id
    return "guest_" + uuid.uuid4().hex[:16]


def memory_for(user: dict[str, Any] | None, guest_session_id: str | None = None) -> tuple[str, str, MemoryManager]:
    if user:
        user_id = user["id"]
        store_path = MEMORY_ROOT / "users" / f"{_safe_store_name(user_id)}.json"
        return user_id, "", MemoryManager(store_path=store_path)

    guest = _guest_id(guest_session_id)
    store_path = MEMORY_ROOT / "guests" / f"{_safe_store_name(guest)}.json"
    return guest, guest.removeprefix("guest_"), MemoryManager(store_path=store_path)


def _conversation_summaries(manager: MemoryManager, user_id: str) -> list[dict[str, Any]]:
    summaries = []
    for item in manager.list_conversations(user_id):
        messages = item.get("messages") or []
        summaries.append(
            {
                "conversation_id": item["conversation_id"],
                "title": item.get("title") or "新的留学咨询",
                "entry_point": item.get("entry_point") or "chat",
                "updated_at": item.get("updated_at"),
                "message_count": item.get("message_count", len(messages)),
                "messages": messages[-20:],
            }
        )
    return summaries


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "qingliuxue-api"}


@app.post("/auth/register", response_model=AuthResponse)
def register(payload: AuthRequest) -> dict[str, Any]:
    try:
        email = validate_email(payload.email)
        validate_password(payload.password)
        user = db.create_user(email=email, password_hash=hash_password(payload.password), display_name=payload.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_access_token(user["id"], extra={"email": user["email"]})
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: AuthRequest) -> dict[str, Any]:
    try:
        email = validate_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = db.get_user_by_email(email, include_password=True)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    public_user = {key: value for key, value in user.items() if key != "password_hash"}
    token = create_access_token(public_user["id"], extra={"email": public_user["email"]})
    return {"access_token": token, "token_type": "bearer", "user": public_user}


@app.get("/auth/me")
def me(user: dict[str, Any] = Depends(required_user)) -> dict[str, Any]:
    return {"user": user}


@app.post("/chat")
def chat(payload: ChatRequest, user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    user_id, guest_session_id, manager = memory_for(user, payload.guest_session_id)
    supervisor = StudyAbroadSupervisor(memory_manager=manager)
    result = supervisor.run(
        query=payload.message.strip(),
        user_id=user_id,
        conversation_id=payload.conversation_id,
        questionnaire=payload.questionnaire,
        requested_agents=payload.requested_agents,
    )
    result["guest_session_id"] = guest_session_id
    result["conversations"] = _conversation_summaries(manager, user_id)
    return result


@app.get("/conversations")
def conversations(
    guest_session_id: str | None = None,
    user: dict[str, Any] | None = Depends(optional_user),
) -> dict[str, Any]:
    user_id, resolved_guest_id, manager = memory_for(user, guest_session_id)
    return {
        "guest_session_id": resolved_guest_id,
        "conversations": _conversation_summaries(manager, user_id),
        "profile": manager.export_user_profile(user_id),
    }


@app.post("/conversations")
def create_conversation(
    payload: ConversationCreateRequest,
    user: dict[str, Any] | None = Depends(optional_user),
) -> dict[str, Any]:
    user_id, guest_session_id, manager = memory_for(user, payload.guest_session_id)
    conversation = manager.create_conversation(user_id=user_id, title=payload.title, entry_point=payload.entry_point)
    return {
        "guest_session_id": guest_session_id,
        "conversation": conversation,
        "conversations": _conversation_summaries(manager, user_id),
    }


@app.post("/questionnaire")
def questionnaire(payload: QuestionnaireRequest, user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    user_id, guest_session_id, manager = memory_for(user, payload.guest_session_id)
    result = StudyAbroadSupervisor(memory_manager=manager).run(
        query="请根据问卷更新我的用户画像。",
        user_id=user_id,
        conversation_id=payload.conversation_id,
        questionnaire=payload.questionnaire,
        requested_agents=["profile"],
    )
    return {
        "guest_session_id": guest_session_id,
        "conversation_id": result["conversation_id"],
        "profile": result["profile"],
        "conversations": _conversation_summaries(manager, user_id),
    }


@app.get("/profile")
def profile(
    guest_session_id: str | None = None,
    user: dict[str, Any] | None = Depends(optional_user),
) -> dict[str, Any]:
    user_id, guest_session_id, manager = memory_for(user, guest_session_id)
    return {"guest_session_id": guest_session_id, "profile": manager.export_user_profile(user_id)}

