# -*- coding: utf-8 -*-
"""Connected chat page for Qingliuxue."""

from __future__ import annotations

import html
import re
import uuid
from textwrap import dedent
from typing import Any

import streamlit as st

try:
    from api_client import ApiClientError
    from api_client import chat_message, create_conversation, list_conversations
    from ui_theme import logo_mark_uri
except ImportError:  # Allows importing as app.frontend.chat_page in tests.
    from app.frontend.api_client import ApiClientError
    from app.frontend.api_client import chat_message, create_conversation, list_conversations
    from app.frontend.ui_theme import logo_mark_uri


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


STARTER_PROMPTS = {
    "direct": [
        ("真实案例路线", "GPA 3.55，有 AI 产品实习，想申请美国 CS/DS 硕士，请按真实案例给路线。"),
        ("补全我的画像", "我还不确定国家和预算，请先问我 3 个关键问题再给方向。"),
        ("国家对比", "预算有限，更看重就业和性价比，英国、加拿大、澳洲怎么选？"),
        ("下一步计划", "如果我想 2027 年秋季入学，接下来 3 个月应该做什么？"),
    ],
    "personalized": [
        ("生成选校路线", "请根据我刚填写的信息，给我冲刺、匹配、保底三档路线。"),
        ("补全风险点", "我的背景里哪些地方最影响申请结果？请优先指出。"),
        ("案例参考", "请找和我最像的真实案例，并解释为什么相似。"),
        ("调整偏好", "请更重视就业导向和预算稳定，重新推荐路线。"),
    ],
    "timeline": [
        ("按月拆任务", "帮我生成 2027 年秋季入学申请时间线，按月份拆任务。"),
        ("先做什么", "我现在信息不完整，请先给一条通用但可执行的申请节奏。"),
        ("考试规划", "把语言考试、GRE/GMAT、选校和文书节点放在同一条线上。"),
        ("风险提醒", "申请时间线里最容易拖延和返工的环节有哪些？"),
    ],
    "essay": [
        ("SOP 主线", "SOP 怎么写才能突出实习、项目和职业目标？"),
        ("素材清单", "请给我一份文书素材收集清单，按重要性排序。"),
        ("中英差异", "美国 SOP 和英国 PS 写法有什么不同？"),
        ("避免踩坑", "中国学生写文书最常见的问题有哪些？"),
    ],
    "comparison": [
        ("三国对比", "预算有限，更看重就业和性价比，英国、加拿大、澳洲怎么选？"),
        ("专业对比", "CS、DS、BA 三个方向从申请难度和就业看怎么选？"),
        ("项目路线", "比较美国 MSBA、英国 Business Analytics 和新加坡数据相关项目。"),
        ("决策矩阵", "请把费用、时长、就业、移民可能性做成对比矩阵。"),
    ],
    "materials": [
        ("材料清单", "申请研究生需要准备哪些材料？推荐信、成绩单、简历有什么坑？"),
        ("推荐信计划", "我应该找什么样的推荐人？每封信重点写什么？"),
        ("提交顺序", "请按时间顺序列出材料准备和提交检查表。"),
        ("认证细节", "成绩单、在读证明、翻译件和公证认证要注意什么？"),
    ],
    "visa": [
        ("签证路径", "拿到录取后签证、住宿、行前和毕业后求职怎么规划？"),
        ("资金证明", "请解释资金证明、存款时间和常见风险点。"),
        ("毕业后规划", "如果目标是毕业后留当地工作，我该提前准备什么？"),
        ("行前清单", "请生成一份入学前 60 天行前清单。"),
    ],
}


def _ensure_state() -> None:
    st.session_state.setdefault("guest_session_id", "gs_" + uuid.uuid4().hex[:16])
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("last_route", [])
    st.session_state.setdefault("last_agent_results", [])
    st.session_state.setdefault("last_call_status", {})


def _token() -> str | None:
    return st.session_state.get("access_token")


def _user_email() -> str | None:
    user = st.session_state.get("current_user") or {}
    return user.get("email")


def _call_agent(message: str, entry: str, requested_agents: list[str] | None = None, questionnaire: dict[str, Any] | None = None) -> dict[str, Any]:
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
    result["transport"] = "api"
    return result


def _store_result(result: dict[str, Any]) -> None:
    st.session_state["last_route"] = result.get("route") or []
    st.session_state["last_agent_results"] = result.get("agent_results") or []
    st.session_state["profile_snapshot"] = result.get("profile") or {}
    st.session_state["last_call_status"] = {
        "transport": result.get("transport") or "api",
        "answer_source": result.get("answer_source") or result.get("llm_source"),
        "api_warning": result.get("api_warning"),
    }


def _append_turn(user_message: str, result: dict[str, Any]) -> None:
    st.session_state["chat_messages"].append({"role": "user", "content": user_message})
    st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
    _store_result(result)


def _append_assistant_result(result: dict[str, Any]) -> None:
    st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
    _store_result(result)


def _append_error(message: str) -> None:
    st.session_state["chat_messages"].append({"role": "system", "content": message})
    st.session_state["last_call_status"] = {"transport": "api_error", "api_warning": message}


def _load_conversations() -> list[dict[str, Any]]:
    try:
        data = list_conversations(token=_token(), guest_session_id=st.session_state["guest_session_id"])
        return data.get("conversations") or []
    except Exception:
        return []


def _conversation_label(item: dict[str, Any]) -> str:
    messages = item.get("messages") or []
    source = ""
    for message in messages:
        if message.get("role") == "user" and message.get("content"):
            source = str(message["content"])
            break
    if not source:
        source = str(item.get("title") or "")

    compact = re.sub(r"\s+", "", source)
    lowered = compact.lower()
    label_rules = [
        (("预算", "性价比", "英国", "加拿大", "澳洲", "国家"), "国家对比"),
        (("gpa", "cs", "ds", "ai", "实习", "案例"), "CS申请路线"),
        (("不确定", "先问", "画像", "关键问题"), "补全画像"),
        (("时间线", "月份", "2027", "任务", "规划"), "时间规划"),
        (("sop", "ps", "文书", "素材", "主线"), "文书主线"),
        (("材料", "推荐信", "成绩单", "简历"), "材料清单"),
        (("签证", "住宿", "行前", "毕业后"), "签证规划"),
    ]
    for keywords, label in label_rules:
        if any(keyword in lowered or keyword in compact for keyword in keywords):
            return label

    source = re.sub(r"[，。！？、,.!?;；:：\"'“”‘’（）()【】\[\]]+", "", compact)
    source = re.sub(r"^(请|帮我|麻烦|我想|我还|如果|关于|生成|分析)+", "", source)
    fallback = "留学咨询"
    if not source or source == "新的留学咨询":
        return fallback
    return source[:8]


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
    st.rerun()


def _render_sidebar(entry: str) -> None:
    logo = logo_mark_uri()
    display_name = _user_email() or "访客"
    user_hint = "长期记忆已开启" if _user_email() else "访客模式，本次关闭后不保留长期记忆"
    with st.sidebar:
        st.markdown(
            dedent(f"""
            <div class="side-shell">
                <div class="side-brand">
                    <span class="side-logo"><img src="{logo}" alt="轻留学" /></span>
                    <span>轻留学</span>
                </div>
                <div class="side-brand-spacer" aria-hidden="true">&nbsp;</div>
            </div>
            """).strip(),
            unsafe_allow_html=True,
        )

        top_left, top_right = st.columns(2)
        with top_left:
            st.markdown('<a class="side-action-link" href="?page=home">返回首页</a>', unsafe_allow_html=True)
        with top_right:
            if st.button("新对话", use_container_width=True):
                _new_chat(entry)

        st.markdown("#### 历史对话")
        conversations = _load_conversations()
        if not conversations:
            st.caption("暂无历史对话。")
        for item in conversations[:10]:
            title = _conversation_label(item)
            if st.button(title, key=f"conv_{item['conversation_id']}", use_container_width=True):
                st.session_state["conversation_id"] = item["conversation_id"]
                st.session_state["chat_messages"] = [
                    {"role": msg.get("role"), "content": msg.get("content", "")}
                    for msg in item.get("messages", [])
                    if msg.get("role") in {"user", "assistant"}
                ]
                st.rerun()

        auth_html = (
            '<a class="side-mini-link" href="?page=logout">退出登录</a>'
            if _user_email()
            else '<a class="side-mini-link" href="?page=login">登录</a><a class="side-mini-link" href="?page=register">注册</a>'
        )
        st.markdown(
            dedent(f"""
            <div class="side-user-card">
                <div class="side-avatar">{display_name[:1].upper()}</div>
                <div class="side-user-meta">
                    <strong>{display_name}</strong>
                    <span>{user_hint}</span>
                </div>
                <div class="side-auth-links">{auth_html}</div>
            </div>
            """).strip(),
            unsafe_allow_html=True,
        )


def _render_agent_trace() -> None:
    status = st.session_state.get("last_call_status") or {}
    if status.get("transport") in {"api_error", "local_fallback"}:
        warning = html.escape(str(status.get("api_warning") or "LLM 调用失败"))
        st.markdown(
            dedent(f"""
            <div class="api-warning">
                没有生成假答案：真实 LLM 调用失败。原因：{warning}
            </div>
            """).strip(),
            unsafe_allow_html=True,
        )


def _message_html(content: str) -> str:
    escaped = html.escape((content or "").strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", escaped) if part.strip()]
    if not paragraphs:
        return "<p>我暂时没有生成结果。</p>"
    return "".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in paragraphs)


def _render_message(role: str, content: str) -> None:
    is_user = role == "user"
    is_error = role == "system"
    role_class = "user" if is_user else ("system" if is_error else "assistant")
    avatar = "你" if is_user else "留"
    st.markdown(
        dedent(f"""
        <div class="ql-msg-row {role_class}">
            <div class="ql-msg-avatar" aria-hidden="true">{avatar}</div>
            <div class="ql-msg-stack">
                <div class="ql-msg-bubble">{_message_html(content)}</div>
            </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def _has_user_turn() -> bool:
    return any(message.get("role") == "user" for message in st.session_state.get("chat_messages", []))


def _starter_prompts(entry: str) -> list[tuple[str, str]]:
    return STARTER_PROMPTS.get(entry) or STARTER_PROMPTS["direct"]


def _render_starters(entry: str) -> None:
    st.markdown(
        dedent("""
        <div class="quick-title">可以直接问</div>
        """).strip(),
        unsafe_allow_html=True,
    )
    cols = st.columns(4, gap="small")
    for index, (title, prompt) in enumerate(_starter_prompts(entry)):
        with cols[index % 4]:
            if st.button(title, key=f"starter_{entry}_{index}", use_container_width=True, help=prompt):
                st.session_state["chat_messages"].append({"role": "user", "content": prompt})
                try:
                    with st.spinner("正在调用真实 LLM..."):
                        result = _call_agent(prompt, entry)
                    st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
                    _store_result(result)
                except ApiClientError as exc:
                    _append_error(str(exc))
                st.rerun()


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
            [data-testid="stStatusWidget"],
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stSidebarHeader"],
            [data-testid="collapsedControl"] {
                display: none !important;
            }
            .stApp {
                background:
                    radial-gradient(circle at 62% 10%, rgba(237, 118, 93, 0.10), transparent 34%),
                    linear-gradient(180deg, #fffaf8 0%, #fff7f3 100%) !important;
            }
            html,
            body,
            #root,
            [data-testid="stAppViewContainer"] {
                background: #fff8f5 !important;
            }
            [data-testid="stSidebar"] {
                display: block !important;
                width: 318px !important;
                min-width: 318px !important;
                background: #f6ded5 !important;
                border-right: 1px solid #e8c5ba;
                box-shadow: 18px 0 44px rgba(124, 47, 34, 0.06);
            }
            [data-testid="stSidebar"] * {
                font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
            }
            [data-testid="stSidebarContent"] {
                padding: 0 16px 16px !important;
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }
            [data-testid="stSidebarUserContent"] {
                padding-top: 14px !important;
            }
            .main .block-container {
                max-width: 1120px !important;
                padding: 8px 40px 128px !important;
            }
            .side-shell {
                display: block;
            }
            .side-brand {
                display: flex;
                align-items: center;
                gap: 12px;
                margin: 0;
                color: #9a3d2c;
                font-size: 23px;
                font-weight: 950;
            }
            .side-logo {
                width: 54px;
                height: 54px;
                padding: 0;
                display: inline-grid;
                place-items: center;
                border-radius: 0;
                background: transparent;
                border: 0;
                box-shadow: none;
                overflow: visible;
            }
            .side-logo img {
                width: 54px;
                height: 54px;
                object-fit: contain;
                display: block;
            }
            .side-brand-spacer {
                height: 14px;
                line-height: 14px;
                font-size: 1px;
                color: transparent;
                overflow: hidden;
            }
            [data-testid="stSidebar"] .stButton button,
            [data-testid="stSidebar"] .stLinkButton a {
                height: 42px;
                border-radius: 12px !important;
                border: 1px solid rgba(184, 79, 59, 0.20) !important;
                color: #7c2f22 !important;
                background: rgba(255, 255, 255, 0.58) !important;
                box-shadow: none !important;
            }
            [data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has([data-testid="stHorizontalBlock"]) {
                margin-top: 16px !important;
            }
            [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
                margin-top: 0 !important;
            }
            .side-action-link {
                height: 42px;
                width: 100%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 12px;
                border: 1px solid rgba(184, 79, 59, 0.20);
                color: #7c2f22 !important;
                background: rgba(255, 255, 255, 0.58);
                font-size: 14px;
                font-weight: 800;
                text-decoration: none !important;
            }
            .side-action-link:hover {
                background: rgba(255, 252, 250, 0.90);
                box-shadow: 0 12px 28px rgba(124, 47, 34, 0.08);
            }
            [data-testid="stSidebar"] h4 {
                margin-top: 22px !important;
                color: #7c2f22 !important;
                font-size: 14px !important;
                letter-spacing: 0;
            }
            [data-testid="stSidebar"] .stCaption {
                color: #8a756c !important;
            }
            .side-user-card {
                position: fixed;
                left: 16px;
                bottom: 16px;
                width: 286px;
                min-height: 74px;
                display: grid;
                grid-template-columns: 42px 1fr auto;
                gap: 10px;
                align-items: center;
                padding: 12px;
                border-radius: 16px;
                border: 1px solid rgba(184, 79, 59, 0.18);
                background: rgba(255, 252, 250, 0.74);
                box-shadow: 0 16px 34px rgba(124, 47, 34, 0.10);
                backdrop-filter: blur(12px);
            }
            .side-avatar {
                width: 42px;
                height: 42px;
                display: grid;
                place-items: center;
                border-radius: 999px;
                color: #fff;
                background: #b94f3b;
                font-size: 16px;
                font-weight: 900;
            }
            .side-user-meta {
                min-width: 0;
                display: grid;
                gap: 3px;
            }
            .side-user-meta strong {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: #2b2724;
                font-size: 14px;
            }
            .side-user-meta span {
                color: #7c716b;
                font-size: 11px;
                line-height: 1.35;
            }
            .side-auth-links {
                display: grid;
                gap: 4px;
                text-align: right;
            }
            .side-mini-link {
                color: #9a3d2c !important;
                font-size: 12px;
                font-weight: 800;
                text-decoration: none !important;
            }
            .ql-message-list {
                width: min(980px, 100%);
                margin: 0 auto 16px;
            }
            .ql-msg-row {
                display: flex;
                gap: 12px;
                align-items: flex-start;
                margin: 16px 0;
            }
            .ql-msg-row.user {
                justify-content: flex-end;
            }
            .ql-msg-row.system {
                justify-content: center;
            }
            .ql-msg-row.user .ql-msg-avatar {
                order: 2;
                background: #b94f3b;
                color: #ffffff;
                border-color: rgba(185, 79, 59, 0.20);
            }
            .ql-msg-row.user .ql-msg-stack {
                align-items: flex-end;
            }
            .ql-msg-row.system .ql-msg-avatar,
            .ql-msg-row.system .ql-msg-label {
                display: none;
            }
            .ql-msg-row.system .ql-msg-stack {
                max-width: min(760px, 100%);
                align-items: center;
            }
            .ql-msg-avatar {
                width: 44px;
                height: 44px;
                flex: 0 0 44px;
                display: grid;
                place-items: center;
                border-radius: 999px;
                color: #9a3d2c;
                background: #fff6f1;
                border: 1px solid #f0e6d9;
                box-shadow: 0 10px 22px rgba(73, 42, 33, 0.06);
                font-size: 15px;
                font-weight: 900;
            }
            .ql-msg-stack {
                max-width: 76%;
                display: flex;
                flex-direction: column;
                gap: 0;
            }
            .ql-msg-label {
                display: none;
            }
            .ql-msg-bubble {
                padding: 16px 20px;
                border-radius: 18px;
                border: 1px solid rgba(240, 230, 217, 0.90);
                background: rgba(255, 253, 249, 0.92);
                color: #2f2b28;
                box-shadow: 0 10px 24px rgba(73, 42, 33, 0.045);
                overflow-wrap: anywhere;
                word-break: break-word;
            }
            .ql-msg-row.user .ql-msg-bubble {
                color: #3a2520;
                background: #f8ded6;
                border-color: #efc4b8;
                box-shadow: none;
            }
            .ql-msg-row.system .ql-msg-bubble {
                color: #8a3427;
                background: rgba(255, 245, 240, 0.92);
                border-color: rgba(205, 122, 94, 0.36);
                box-shadow: none;
            }
            .ql-msg-bubble p {
                margin: 0 0 12px;
                font-size: 16px;
                line-height: 1.78;
                font-weight: 540;
            }
            .ql-msg-bubble p:last-child {
                margin-bottom: 0;
            }
            .ql-msg-bubble strong {
                font-weight: 850;
                color: inherit;
            }
            .stButton button,
            .stLinkButton a {
                border-radius: 14px !important;
                border-color: rgba(231, 185, 170, 0.95) !important;
                color: #9a3d2c !important;
                background: rgba(255, 252, 250, 0.72) !important;
                font-weight: 800 !important;
                transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
            }
            .stButton button:hover,
            .stLinkButton a:hover {
                transform: translateY(-1px);
                background: rgba(255, 247, 244, 0.96) !important;
                box-shadow: 0 12px 28px rgba(124, 47, 34, 0.10);
            }
            .stChatMessage {
                max-width: min(820px, 100%);
                margin: 0 auto 14px;
                padding: 14px 16px;
                border-radius: 18px;
                border: 1px solid rgba(234, 217, 210, 0.88);
                background: rgba(255, 252, 250, 0.82);
                box-shadow: 0 14px 34px rgba(73, 42, 33, 0.045);
                overflow-wrap: anywhere;
                word-break: break-word;
            }
            .stChatMessage:has([data-testid="chatAvatarIcon-user"]),
            .stChatMessage:has([data-testid="stChatMessageAvatarUser"]) {
                background: rgba(255, 239, 233, 0.74);
            }
            .stChatMessage p {
                line-height: 1.85;
                font-size: 16px;
            }
            [data-testid="stExpander"] {
                max-width: min(820px, 100%);
                margin: 6px auto 22px;
                border-color: rgba(234, 217, 210, 0.8) !important;
                border-radius: 14px !important;
                background: rgba(255, 252, 250, 0.62) !important;
            }
            .quick-title {
                max-width: min(980px, 100%);
                margin: 18px auto 10px;
                color: #7c2f22;
                font-size: 16px;
                font-weight: 900;
            }
            .main div[data-testid="stHorizontalBlock"] .stButton button {
                min-height: 48px !important;
                padding: 10px 16px !important;
                justify-content: center !important;
                text-align: center !important;
                white-space: normal !important;
                line-height: 1.25 !important;
                color: #8a3427 !important;
                background: rgba(255, 252, 250, 0.88) !important;
                border-radius: 999px !important;
                border-color: rgba(231, 185, 170, 0.90) !important;
                box-shadow: 0 8px 20px rgba(73, 42, 33, 0.035) !important;
                font-size: 15px !important;
            }
            [data-testid="stChatInput"] textarea {
                border: 0 !important;
                box-shadow: none !important;
                background: transparent !important;
                min-height: 44px !important;
                padding: 12px 4px !important;
                color: #2b2724 !important;
                font-size: 15px !important;
            }
            [data-testid="stChatInput"] {
                max-width: 820px;
                margin: 0 auto;
            }
            [data-testid="stChatInput"] > div {
                min-height: 64px !important;
                border-radius: 20px !important;
                border: 1px solid rgba(240, 230, 217, 0.95) !important;
                background: rgba(255, 255, 255, 0.96) !important;
                box-shadow: 0 16px 42px rgba(73, 42, 33, 0.09);
                padding: 8px 10px 8px 18px !important;
            }
            [data-testid="stChatInput"] button {
                width: 40px !important;
                height: 40px !important;
                border-radius: 12px !important;
                background: #f0dfd8 !important;
                color: #9a3d2c !important;
                border: 0 !important;
                box-shadow: none !important;
            }
            [data-testid="stChatInput"] button:hover {
                background: #e8cabf !important;
            }
            .api-warning {
                width: min(980px, 100%);
                margin: 8px auto 16px;
                padding: 10px 14px;
                border-radius: 12px;
                border: 1px solid rgba(205, 122, 94, 0.35);
                background: rgba(255, 245, 240, 0.88);
                color: #8a3427;
                font-size: 13px;
                line-height: 1.5;
                font-weight: 700;
            }
            div[data-testid="stHorizontalBlock"] button {
                white-space: normal !important;
                line-height: 1.55 !important;
            }
            pre, code {
                white-space: pre-wrap !important;
                word-break: break-word !important;
            }
            @media (max-width: 900px) {
                [data-testid="stSidebar"] {
                    width: 284px !important;
                    min-width: 284px !important;
                }
                .side-user-card {
                    width: 252px;
                }
                .main .block-container {
                    padding: 6px 18px 112px !important;
                }
                .ql-msg-stack {
                    max-width: 82%;
                }
                .ql-msg-avatar,
                .ql-msg-label {
                    display: none;
                }
                .main div[data-testid="stHorizontalBlock"] .stButton button {
                    min-height: 44px !important;
                    padding: 9px 12px !important;
                    font-size: 14px !important;
                }
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

    st.markdown('<div class="ql-message-list">', unsafe_allow_html=True)
    for message in st.session_state.get("chat_messages", []):
        _render_message(message.get("role", "assistant"), message.get("content", ""))
    st.markdown("</div>", unsafe_allow_html=True)

    _render_agent_trace()

    if not _has_user_turn():
        _render_starters(entry)

    if user_input := st.chat_input("告诉我你的 GPA、专业、目标，或继续问我..."):
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        try:
            with st.spinner("正在调用真实 LLM..."):
                result = _call_agent(user_input, entry)
            st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
            _store_result(result)
        except ApiClientError as exc:
            _append_error(str(exc))
        st.rerun()
