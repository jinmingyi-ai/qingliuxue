# -*- coding: utf-8 -*-
"""Smoke test for auth, memory and agent API flow."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tempfile.gettempdir()) / f"qingliuxue_test_{uuid.uuid4().hex}.db")
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ALLOW_DETERMINISTIC_CHAT_FALLBACK"] = "1"

from app.backend.api.main import app  # noqa: E402


def expect(condition: bool, label: str) -> None:
    print(f"{label}: {'PASS' if condition else 'FAIL'}")
    if not condition:
        raise AssertionError(label)


def main() -> None:
    client = TestClient(app)
    email = f"student_{uuid.uuid4().hex[:8]}@example.com"
    password = "demo12345"

    register = client.post("/auth/register", json={"email": email, "password": password, "display_name": "Demo"})
    expect(register.status_code == 200, "register")
    token = register.json()["access_token"]

    login = client.post("/auth/login", json={"email": email, "password": password})
    expect(login.status_code == 200, "login")
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/auth/me", headers=headers)
    expect(me.status_code == 200 and me.json()["user"]["email"] == email, "auth_me")

    questionnaire = {
        "current_level": "本科毕业",
        "undergraduate_school": "某 211 大学",
        "undergraduate_major": "信息管理",
        "score_type": "绩点（4.0 制）",
        "score_value": "3.55",
        "language_type": "TOEFL",
        "language_score": "101",
        "experiences": ["实习", "产品/项目落地"],
        "application_year": "2027",
        "target_countries": ["美国"],
        "target_majors": ["计算机/数据/AI"],
        "budget": ["50-70 万"],
        "priorities": ["就业结果", "留在当地工作的可能性"],
    }
    q_resp = client.post("/questionnaire", headers=headers, json={"questionnaire": questionnaire})
    expect(q_resp.status_code == 200, "questionnaire")
    profile = q_resp.json()["profile"]
    expect(profile["academic"]["gpa"] == 3.55, "questionnaire_gpa_memory")

    chat = client.post(
        "/chat",
        headers=headers,
        json={
            "message": "帮我推荐美国 CS 硕士路线，并给时间线和文书策略。",
            "requested_agents": ["case", "timeline", "essay"],
        },
    )
    expect(chat.status_code == 200, "chat")
    data = chat.json()
    expect(data["route"] == ["profile", "case", "timeline", "essay"], "agent_route")
    expect(len(data["agent_results"]) == 4, "agent_results")
    expect(data["conversations"], "conversation_saved")

    conversations = client.get("/conversations", headers=headers)
    expect(conversations.status_code == 200 and conversations.json()["conversations"], "list_conversations")
    expect(conversations.json()["profile"]["academic"]["gpa"] == 3.55, "long_term_profile")

    guest = client.post(
        "/chat",
        json={"message": "我想先看看英国商科路线", "guest_session_id": "guesttest123", "requested_agents": ["case"]},
    )
    expect(guest.status_code == 200 and guest.json()["guest_session_id"] == "guesttest123", "guest_chat")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
