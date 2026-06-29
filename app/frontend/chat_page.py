# -*- coding: utf-8 -*-
"""Connected chat page for Qingliuxue."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from textwrap import dedent
from typing import Any

import streamlit as st

try:
    from api_client import chat_message, create_conversation, list_conversations
    from ui_theme import base_page_css, logo_uri
except ImportError:  # Allows importing as app.frontend.chat_page in tests.
    from app.frontend.api_client import chat_message, create_conversation, list_conversations
    from app.frontend.ui_theme import base_page_css, logo_uri


ENTRY_CONFIG = {
    "direct": {
        "title": "真实案例路线推荐",
        "seed": "请基于真实案例库，给我生成一条当前比较热门且可执行的留学路线。",
        "agents": ["case"],
        "description": "先用案例库给一条可参考路线，再根据聊天继续收集画像。",
    },
    "personalized": {
        "title": "个性化智能选校",
        "seed": "请根据我已经填写的问卷和现有用户画像，生成一版个性化智能选校路线。",
        "agents": ["case"],
        "description": "结合问卷、长期记忆和真实案例做选校路线。",
    },
    "timeline": {
        "title": "时间线和任务规划",
        "seed": "请根据我的画像生成申请时间线和任务规划；如果信息不足，请先给一条常见路线。",
        "agents": ["timeline"],
        "description": "按国家、项目和入学季生成阶段性任务表。",
    },
    "essay": {
        "title": "文书策略和指导",
        "seed": "请根据我的画像和文书知识库，生成 SOP/PS 文书策略和素材准备方向。",
        "agents": ["essay"],
        "description": "结合你的经历和目标项目，梳理文书主线、素材和表达重点。",
    },
    "comparison": {
        "title": "多方案对比",
        "seed": "请结合我的画像，比较几个适合我的留学国家、专业或项目方案。",
        "agents": ["comparison"],
        "description": "把国家、专业、预算、就业和申请难度放在同一张表里比较。",
    },
    "materials": {
        "title": "材料准备指导",
        "seed": "请根据我的画像和材料知识库，生成申请材料准备清单和注意事项。",
        "agents": ["materials"],
        "description": "生成申请材料清单、准备顺序和容易遗漏的细节。",
    },
    "visa": {
        "title": "签证和毕业后规划",
        "seed": "请根据我的画像，生成签证、入学后准备和毕业后路径规划。",
        "agents": ["visa"],
        "description": "规划签证、入学衔接、工签窗口和毕业后发展路径。",
    },
}


QUICK_PROMPTS = [
    "我 GPA 3.55，本科信息管理，有两段 AI 产品实习，想申请美国 CS 或 DS 硕士，请推荐真实案例路线。",
    "帮我生成 2027 年秋季入学的申请时间线，按月份列任务。",
    "我的预算比较有限，更看重就业和性价比，英国、加拿大、澳洲怎么选？",
    "我想申请商科或数据分析，请帮我比较美国 MSBA、英国 Business Analytics 和新加坡相关项目。",
    "SOP 应该怎么写才能突出实习、项目和职业目标？",
    "申请美国研究生需要准备哪些材料？推荐信、成绩单、简历有什么坑？",
    "拿到录取后签证、住宿、行前和毕业后求职应该怎么规划？",
    "请记住：我更喜欢就业导向、预算稳一点、希望毕业后留当地工作。",
]


def _ensure_state() -> None:
    st.session_state.setdefault("guest_session_id", "gs_" + uuid.uuid4().hex[:16])
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("last_route", [])
    st.session_state.setdefault("last_agent_results", [])
    st.session_state.setdefault("entry_initialized", {})


def _token() -> str | None:
    return st.session_state.get("access_token")


def _user_email() -> str | None:
    user = st.session_state.get("current_user") or {}
    return user.get("email")


def _direct_memory_manager():
    from app.backend.memory.memory_manager import MemoryManager

    if _token() and st.session_state.get("current_user"):
        user_id = st.session_state["current_user"]["id"]
        store_path = Path("app/data/memory/users") / f"{user_id}.json"
    else:
        user_id = "guest_" + st.session_state["guest_session_id"]
        store_path = Path(tempfile.gettempdir()) / "qingliuxue_guests" / f"{user_id}.json"
    return user_id, MemoryManager(store_path=store_path)


def _local_supervisor_call(message: str, entry: str, requested_agents: list[str] | None, questionnaire: dict[str, Any] | None) -> dict[str, Any]:
    from app.backend.agents.supervisor import StudyAbroadSupervisor

    user_id, manager = _direct_memory_manager()
    result = StudyAbroadSupervisor(memory_manager=manager).run(
        query=message,
        user_id=user_id,
        conversation_id=st.session_state.get("conversation_id"),
        questionnaire=questionnaire,
        requested_agents=requested_agents,
    )
    st.session_state["conversation_id"] = result["conversation_id"]
    result["conversations"] = manager.list_conversations(user_id)
    result["local_fallback"] = True
    return result


def _call_agent(message: str, entry: str, requested_agents: list[str] | None = None, questionnaire: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = chat_message(
            message=message,
            token=_token(),
            conversation_id=st.session_state.get("conversation_id"),
            entry=entry,
            requested_agents=requested_agents,
            questionnaire=questionnaire,
            guest_session_id=st.session_state["guest_session_id"],
        )
        st.session_state["conversation_id"] = result.get("conversation_id")
        if result.get("guest_session_id"):
            st.session_state["guest_session_id"] = result["guest_session_id"]
        return result
    except Exception as exc:
        result = _local_supervisor_call(message, entry, requested_agents, questionnaire)
        result["api_warning"] = str(exc)
        return result


def _store_result(result: dict[str, Any]) -> None:
    st.session_state["last_route"] = result.get("route") or []
    st.session_state["last_agent_results"] = result.get("agent_results") or []
    st.session_state["profile_snapshot"] = result.get("profile") or {}


def _append_turn(user_message: str, result: dict[str, Any]) -> None:
    st.session_state["chat_messages"].append({"role": "user", "content": user_message})
    st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
    _store_result(result)


def _initialise_entry(entry: str) -> None:
    config = ENTRY_CONFIG.get(entry, ENTRY_CONFIG["direct"])
    key = f"{entry}:{st.session_state.get('conversation_id') or 'new'}"
    if st.session_state["entry_initialized"].get(key):
        return
    st.session_state["entry_initialized"][key] = True
    questionnaire = st.session_state.pop("pending_questionnaire", None)
    st.session_state["chat_messages"].append(
        {
            "role": "assistant",
            "content": f"我已经进入「{config['title']}」模式，正在根据你的入口和已有信息准备第一版建议。",
        }
    )
    with st.spinner("正在生成第一版建议..."):
        result = _call_agent(config["seed"], entry, config["agents"], questionnaire=questionnaire)
    _append_turn(config["seed"], result)


def _load_conversations() -> list[dict[str, Any]]:
    try:
        data = list_conversations(token=_token(), guest_session_id=st.session_state["guest_session_id"])
        return data.get("conversations") or []
    except Exception:
        return []


def _new_chat(entry: str) -> None:
    st.session_state["chat_messages"] = []
    st.session_state["last_route"] = []
    st.session_state["last_agent_results"] = []
    try:
        data = create_conversation(
            token=_token(),
            entry_point=entry,
            guest_session_id=st.session_state["guest_session_id"],
        )
        st.session_state["conversation_id"] = data.get("conversation", {}).get("conversation_id")
    except Exception:
        st.session_state["conversation_id"] = None
    st.session_state["entry_initialized"] = {}
    st.rerun()


def _render_sidebar(entry: str) -> None:
    logo = logo_uri()
    with st.sidebar:
        st.markdown(
            dedent(f"""
            <div class="side-brand">
                <span class="side-logo"><img src="{logo}" alt="轻留学" /></span>
                <span>轻留学</span>
            </div>
            """).strip(),
            unsafe_allow_html=True,
        )
        if _user_email():
            st.caption(f"已登录：{_user_email()}")
        else:
            st.caption("访客模式：可完整使用，但关闭会话后不保留长期记忆。")

        if st.button("＋ 开启新聊天", use_container_width=True):
            _new_chat(entry)
        st.link_button("返回首页", "?page=home", use_container_width=True)
        if _user_email():
            st.link_button("退出登录", "?page=logout", use_container_width=True)
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.link_button("登录", "?page=login", use_container_width=True)
            with col2:
                st.link_button("注册", "?page=register", use_container_width=True)

        st.markdown("#### 历史对话")
        conversations = _load_conversations()
        if not conversations:
            st.caption("暂无历史对话。")
        for item in conversations[:10]:
            title = item.get("title") or "新的留学咨询"
            if st.button(title, key=f"conv_{item['conversation_id']}", use_container_width=True):
                st.session_state["conversation_id"] = item["conversation_id"]
                st.session_state["chat_messages"] = [
                    {"role": msg.get("role"), "content": msg.get("content", "")}
                    for msg in item.get("messages", [])
                    if msg.get("role") in {"user", "assistant"}
                ]
                st.session_state["entry_initialized"] = {}
                st.rerun()


def _render_agent_trace() -> None:
    route = st.session_state.get("last_route") or []
    results = st.session_state.get("last_agent_results") or []
    if route:
        label_map = {
            "profile": "画像更新",
            "case": "案例推荐",
            "timeline": "时间规划",
            "essay": "文书指导",
            "comparison": "方案对比",
            "materials": "材料指导",
            "visa": "签证与发展",
        }
        st.caption("本轮处理：" + " → ".join(label_map.get(item, item) for item in route))
    if results:
        with st.expander("查看处理过程和参考来源", expanded=False):
            for result in results:
                st.markdown(f"**{result.get('task')}**")
                st.write(result.get("answer", ""))
                sources = result.get("sources") or []
                if sources:
                    st.caption("来源/召回：" + "；".join(str(source.get("id") or source.get("type")) for source in sources[:4]))


def _styles() -> str:
    return dedent("""
        <style>
            :root {
                --coral-900: #7c2f22;
                --coral-800: #9a3d2c;
                --coral-700: #b94f3b;
                --coral-600: #d8614a;
                --coral-200: #f8d8cf;
                --coral-100: #fbebe6;
                --coral-050: #fff8f5;
                --ink: #2b2724;
                --muted: #7c716b;
                --line: #ead9d2;
            }
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            [data-testid="stStatusWidget"] {
                display: none !important;
            }
            .stApp {
                background:
                    radial-gradient(circle at 56% 12%, rgba(237, 118, 93, 0.10), transparent 34%),
                    linear-gradient(180deg, #fffaf8 0%, #fff7f3 100%);
            }
            [data-testid="stSidebar"] {
                display: block !important;
                background: #f6ded5;
                border-right: 1px solid #ead1c8;
                min-width: 300px !important;
            }
            [data-testid="stSidebar"] * {
                font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
            }
            [data-testid="collapsedControl"] {
                display: block !important;
                color: #9a3d2c;
            }
            .main .block-container {
                max-width: 1120px !important;
                padding: 34px 44px 92px !important;
            }
            .side-brand {
                display: flex;
                align-items: center;
                gap: 10px;
                margin: 10px 0 18px;
                color: #9a3d2c;
                font-size: 22px;
                font-weight: 950;
            }
            .side-logo {
                width: 42px;
                height: 42px;
                padding: 5px;
                display: inline-grid;
                place-items: center;
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.92);
                box-shadow: 0 10px 20px rgba(124, 47, 34, 0.12);
            }
            .side-logo img { width: 32px; height: 32px; object-fit: contain; }
            .chat-head {
                padding-bottom: 22px;
                border-bottom: 1px solid #ead9d2;
                margin-bottom: 22px;
            }
            .chat-head h1 {
                margin: 0;
                color: #2b2724;
                font-size: 40px;
                font-weight: 950;
            }
            .chat-head p {
                margin: 8px 0 0;
                color: #7c716b;
                font-size: 17px;
                line-height: 1.7;
                font-weight: 650;
            }
            .stButton button,
            .stLinkButton a {
                border-radius: 10px !important;
                border-color: #e7b9aa !important;
                color: #9a3d2c !important;
                background: rgba(255, 255, 255, 0.72) !important;
                font-weight: 800 !important;
            }
            .stChatMessage {
                border-radius: 14px;
                border: 1px solid #ead9d2;
                background: rgba(255, 252, 250, 0.78);
                overflow-wrap: anywhere;
                word-break: break-word;
                max-width: 100%;
            }
            .stChatMessage p {
                line-height: 1.85;
                font-size: 16px;
            }
            [data-testid="stChatInput"] textarea {
                border-color: #e7b9aa !important;
                box-shadow: 0 0 0 1px rgba(237, 118, 93, 0.08);
            }
            div[data-testid="stHorizontalBlock"] button {
                min-height: 42px;
                white-space: normal !important;
                line-height: 1.55 !important;
            }
            pre, code {
                white-space: pre-wrap !important;
                word-break: break-word !important;
            }
        </style>
        """).strip()


def render(entry: str = "direct") -> None:
    _ensure_state()
    entry = entry if entry in ENTRY_CONFIG else "direct"
    if hasattr(st, "html"):
        st.html(_styles())
    else:
        st.markdown(_styles(), unsafe_allow_html=True)
    _render_sidebar(entry)

    config = ENTRY_CONFIG[entry]
    st.markdown(
        dedent(f"""
        <div class="chat-head">
            <h1>{config["title"]}</h1>
            <p>{config["description"]}</p>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("chat_messages"):
        _initialise_entry(entry)

    for message in st.session_state.get("chat_messages", []):
        role = message.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(message.get("content", ""))

    _render_agent_trace()

    st.markdown("##### 可以直接问")
    cols = st.columns(2)
    for index, prompt in enumerate(QUICK_PROMPTS):
        with cols[index % 2]:
            if st.button(prompt, key=f"quick_{index}", use_container_width=True):
                with st.spinner("正在生成回答..."):
                    result = _call_agent(prompt, entry)
                _append_turn(prompt, result)
                st.rerun()

    if user_input := st.chat_input("输入你的背景、目标、偏好，或继续追问..."):
        with st.spinner("正在生成回答..."):
            result = _call_agent(user_input, entry)
        _append_turn(user_input, result)
        st.rerun()
