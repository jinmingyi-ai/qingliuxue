# -*- coding: utf-8 -*-
"""Smoke tests for Streamlit page rendering.

This catches regressions where full HTML is accidentally rendered as Markdown
text/code, and verifies every top-level route can run without exceptions.
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

APP = ROOT / "app" / "frontend" / "streamlit_app.py"
PAGES = [
    {"page": "home"},
    {"page": "school"},
    {"page": "planning"},
    {"page": "materials"},
    {"page": "login"},
    {"page": "register"},
    {"page": "step1"},
    {"page": "step2"},
    {"page": "step3"},
    {"page": "chat", "entry": "direct"},
    {"page": "chat", "entry": "timeline"},
    {"page": "chat", "entry": "essay"},
    {"page": "chat", "entry": "comparison"},
    {"page": "chat", "entry": "materials"},
    {"page": "chat", "entry": "visa"},
]


def expect(condition: bool, label: str) -> None:
    print(f"{label}: {'PASS' if condition else 'FAIL'}")
    if not condition:
        raise AssertionError(label)


def page_label(params: dict[str, str]) -> str:
    suffix = f":{params['entry']}" if "entry" in params else ""
    return params["page"] + suffix


def collect_visible_text(at: AppTest) -> str:
    parts: list[str] = []
    for collection_name in [
        "markdown",
        "caption",
        "header",
        "subheader",
        "title",
        "code",
        "button",
        "link_button",
    ]:
        collection = getattr(at, collection_name, [])
        for item in collection:
            value = getattr(item, "value", "") or getattr(item, "label", "")
            if value:
                parts.append(str(value))
    return "\n".join(parts)


def collect_code_text(at: AppTest) -> str:
    return "\n".join(str(getattr(item, "value", "")) for item in at.code)


def main() -> None:
    for params in PAGES:
        label = page_label(params)
        at = AppTest.from_file(APP, default_timeout=30)
        for key, value in params.items():
            at.query_params[key] = value
        at.run(timeout=30)

        expect(len(at.exception) == 0, f"{label}_no_exception")
        text = collect_visible_text(at)
        expect("<div class=\"ql-page\"" not in text, f"{label}_no_ql_page_leak")
        expect("<style>" not in text, f"{label}_no_style_leak")
        if params["page"] == "chat":
            expect("轻留学" in text, f"{label}_custom_chat_shell")
            expect(len(at.chat_input) >= 1, f"{label}_chat_input")
            expect("ql-empty-state" in text, f"{label}_empty_welcome_state")
            expect("Agent" in text, f"{label}_agent_description")
            code_text = collect_code_text(at)
            expect("ql-starter-card" not in code_text, f"{label}_no_starter_html_code_leak")
            expect("返回首页" in text, f"{label}_sidebar_home")
            expect("新对话" in text, f"{label}_sidebar_new_chat")
            expect("历史对话" in text, f"{label}_sidebar_history")
            expect("访客" in text, f"{label}_guest_user_card")
            expect("我按你的问题拆给对应的专业模块处理了" not in text, f"{label}_no_deterministic_answer")
            expect("请根据我的画像" not in text, f"{label}_no_internal_seed_prompt")
            expect("keyboard_double" not in text, f"{label}_no_keyboard_double_leak")

    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["page"] = "chat"
    at.query_params["entry"] = "timeline"
    at.query_params["fresh"] = "1"
    at.session_state["chat_messages"] = [{"role": "user", "content": "旧对话"}]
    at.session_state["chat_active_entry"] = "timeline"
    at.run(timeout=30)
    expect(len(at.exception) == 0, "chat_fresh_no_exception")
    expect(at.session_state["chat_messages"] == [], "chat_fresh_clears_messages")
    expect(at.query_params.get("fresh") is None, "chat_fresh_param_consumed")

    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["page"] = "chat"
    at.query_params["entry"] = "direct"
    at.query_params["starter"] = "0"
    at.run(timeout=30)
    expect(len(at.exception) == 0, "chat_starter_query_no_exception")
    expect(at.session_state["chat_messages"][0]["role"] == "user", "chat_starter_query_adds_user_message")
    expect(at.query_params.get("starter") is None, "chat_starter_query_consumed")

    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["page"] = "chat"
    at.query_params["entry"] = "direct"
    at.session_state["chat_active_entry"] = "direct"
    at.session_state["chat_messages"] = [{"role": "user", "content": "测试头像"}]
    at.run(timeout=30)
    message_text = collect_visible_text(at)
    expect('<div class="ql-msg-avatar" aria-hidden="true">我</div>' in message_text, "chat_user_avatar_is_me")
    expect('<div class="ql-msg-avatar" aria-hidden="true">你</div>' not in message_text, "chat_user_avatar_not_you")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
