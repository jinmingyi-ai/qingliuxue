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
            expect(len(at.chat_message) >= 1, f"{label}_chat_messages")
            expect(len(at.chat_input) >= 1, f"{label}_chat_input")
            expect("返回首页" in text, f"{label}_sidebar_home")
            expect("新对话" in text, f"{label}_sidebar_new_chat")
            expect("历史对话" in text, f"{label}_sidebar_history")
            expect("访客" in text, f"{label}_guest_user_card")
            expect("真实案例路线" in text, f"{label}_quick_cards")
            expect("请根据我的画像" not in text, f"{label}_no_internal_seed_prompt")

    print("ALL PASSED")


if __name__ == "__main__":
    main()
