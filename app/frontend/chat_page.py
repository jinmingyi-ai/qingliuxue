# -*- coding: utf-8 -*-
"""Connected chat page for Qingliuxue."""

from __future__ import annotations

import html
import random
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
        "title": "真实案例路线 Agent",
        "seed": "请基于真实案例库，给我生成一条当前比较热门且可执行的留学路线。",
        "agents": ["case"],
        "description": "先参考真实申请案例给出路线，再通过对话补全背景、目标和风险点。",
    },
    "personalized": {
        "title": "智能选校 Agent",
        "seed": "请根据我已经填写的问卷和现有用户画像，生成一版个性化智能选校路线。",
        "agents": ["case"],
        "description": "结合问卷、用户画像和案例库，生成冲刺、匹配、保底的选校路线。",
    },
    "timeline": {
        "title": "时间线规划 Agent",
        "seed": "请根据我的画像生成申请时间线和任务规划；如果信息不足，请先给一条常见路线。",
        "agents": ["timeline"],
        "description": "按入学季、国家和申请阶段，把考试、文书、网申和签证拆成任务。",
    },
    "essay": {
        "title": "文书指导 Agent",
        "seed": "请根据我的画像和文书知识库，生成 SOP/PS 文书策略和素材准备方向。",
        "agents": ["essay"],
        "description": "根据经历、专业方向和目标项目，梳理 SOP/PS 主线、素材和表达重点。",
    },
    "comparison": {
        "title": "多方案对比 Agent",
        "seed": "请结合我的画像，比较几个适合我的留学国家、专业或项目方案。",
        "agents": ["comparison"],
        "description": "把国家、专业、费用、签证、就业和申请难度放在同一张表里比较。",
    },
    "materials": {
        "title": "材料准备 Agent",
        "seed": "请根据我的画像和材料知识库，生成申请材料准备清单和注意事项。",
        "agents": ["materials"],
        "description": "生成材料 checklist、准备顺序、推荐信重点和容易遗漏的提交细节。",
    },
    "visa": {
        "title": "签证规划 Agent",
        "seed": "请根据我的画像，生成签证、入学后准备和毕业后路径规划。",
        "agents": ["visa"],
        "description": "梳理签证、资金证明、行前准备、工签窗口和毕业后发展路径。",
    },
}


STARTER_PROMPTS = {
    "direct": [
        "帮我按真实案例生成一条美国 CS/DS 硕士路线，说明冲刺、匹配、保底。",
        "我还没确定国家和预算，请先问我 3 个关键问题再给方向。",
        "预算 35-45 万，更看重就业，英国、加拿大、澳洲怎么选？",
        "我想 2027 秋入学，请列出接下来 3 个月的优先任务。",
        "本科 GPA 3.3，实习普通，想申请教育学硕士，怎么包装优势？",
        "请找一条适合普通背景学生的稳妥留学路线，并说明关键取舍。",
    ],
    "personalized": [
        "根据我刚填的信息，给我一版冲刺、匹配、保底选校路线。",
        "请指出我背景里最影响录取的 3 个风险点和补强办法。",
        "帮我找相似案例，并说明我该参考哪些做法。",
        "在就业和预算优先的前提下，重新排序申请国家和项目。",
        "如果我的科研不强，请推荐更适合普通背景的项目组合。",
        "请基于我的偏好，列出最需要马上确认的 3 个申请条件。",
    ],
    "timeline": [
        "我计划 2027 秋入学，请按月份生成申请时间线。",
        "请把语言考试、选校、文书、网申拆成阶段任务。",
        "我现在准备晚了，请列出未来 8 周必须完成的事。",
        "帮我标出申请季最容易拖延和返工的节点。",
        "我大三下才开始准备，请生成一条尽量稳妥的节奏。",
        "请按英国申请季，列出每个月的材料和提交重点。",
    ],
    "essay": [
        "我的经历比较普通，SOP 怎样写出清晰主线？",
        "帮我整理文书素材清单，按重要性排序。",
        "美国 SOP 和英国 PS 的写法差异，请用教育学方向举例。",
        "请指出中国学生文书常见空泛表达，并给替换思路。",
        "我只有普通实习和课程项目，PS 该突出哪些细节？",
        "帮我把科研、实习和职业目标连成一条文书逻辑。",
    ],
    "comparison": [
        "教育学、心理学、TESOL、社工这几个方向该怎么选？",
        "英国 vs 加拿大教育学硕士，请从费用、签证和就业对比。",
        "CS、DS、BA 三个方向，从申请难度和就业做矩阵。",
        "我预算有限，请比较 3 个性价比更高的国家方案。",
        "美国一年制项目和英国授课型硕士，适合哪些学生？",
        "请把费用、时长、就业、留下工作的可能性做成对比表。",
    ],
    "materials": [
        "申请教育学硕士，请生成材料 checklist 和准备顺序。",
        "推荐信找谁更合适？请分别设计每封信重点。",
        "成绩单、在读证明、翻译和认证要按什么顺序做？",
        "简历和文书素材怎样准备，才不会后期返工？",
        "申请英国和美国项目，材料准备上最容易混淆什么？",
        "请列出网申提交前必须二次检查的材料细节。",
    ],
    "visa": [
        "拿到录取后，请生成签证、住宿、行前的 60 天清单。",
        "资金证明需要注意什么？请列出常见风险点。",
        "目标毕业后留当地工作，我现在该准备哪些能力？",
        "英国、加拿大、澳洲毕业后工签路径有什么差异？",
        "请按时间顺序列出录取后到入学前的关键事项。",
        "如果担心签证被卡，需要提前准备哪些解释材料？",
    ],
}


def _ensure_state() -> None:
    st.session_state.setdefault("guest_session_id", "gs_" + uuid.uuid4().hex[:16])
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("last_route", [])
    st.session_state.setdefault("last_agent_results", [])
    st.session_state.setdefault("last_call_status", {})
    st.session_state.setdefault("pending_chat_request", None)
    st.session_state.setdefault("starter_prompt_entry", None)
    st.session_state.setdefault("starter_prompt_sample", [])
    st.session_state.setdefault("chat_active_entry", None)


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


def _reset_chat_view(entry: str, keep_questionnaire: bool = True) -> None:
    questionnaire = st.session_state.get("pending_questionnaire") if keep_questionnaire else None
    st.session_state["chat_messages"] = []
    st.session_state["conversation_id"] = None
    st.session_state["last_route"] = []
    st.session_state["last_agent_results"] = []
    st.session_state["last_call_status"] = {}
    st.session_state["pending_chat_request"] = None
    st.session_state["starter_prompt_entry"] = None
    st.session_state["starter_prompt_sample"] = []
    st.session_state["chat_active_entry"] = entry
    if keep_questionnaire and questionnaire is not None:
        st.session_state["pending_questionnaire"] = questionnaire


def _queue_chat_request(
    message: str,
    entry: str,
    requested_agents: list[str] | None = None,
    questionnaire: dict[str, Any] | None = None,
) -> None:
    st.session_state["chat_messages"].append({"role": "user", "content": message})
    st.session_state["pending_chat_request"] = {
        "message": message,
        "entry": entry,
        "requested_agents": requested_agents,
        "questionnaire": questionnaire,
    }


def _process_pending_chat(entry: str) -> None:
    pending = st.session_state.get("pending_chat_request")
    if not pending:
        return

    try:
        result = _call_agent(
            pending["message"],
            pending.get("entry") or entry,
            requested_agents=pending.get("requested_agents"),
            questionnaire=pending.get("questionnaire"),
        )
        st.session_state["chat_messages"].append({"role": "assistant", "content": result.get("answer", "我暂时没有生成结果。")})
        _store_result(result)
        if pending.get("questionnaire") is not None:
            st.session_state.pop("pending_questionnaire", None)
    except ApiClientError as exc:
        _append_error(str(exc))
    finally:
        st.session_state["pending_chat_request"] = None
    st.rerun()


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
    _reset_chat_view(entry)
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
    avatar = "我" if is_user else "留"
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


def _render_thinking_message() -> None:
    st.markdown(
        dedent("""
        <div class="ql-msg-row assistant thinking">
            <div class="ql-msg-avatar" aria-hidden="true">留</div>
            <div class="ql-thinking-inline" aria-live="polite">
                <span>正在思考</span><span class="ql-thinking-dots"><i></i><i></i><i></i></span>
            </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def _has_user_turn() -> bool:
    return any(message.get("role") == "user" for message in st.session_state.get("chat_messages", []))


def _entry_agents(entry: str) -> list[str] | None:
    agents = ENTRY_CONFIG.get(entry, {}).get("agents") or []
    return list(agents) if agents else None


def _pending_questionnaire(entry: str) -> dict[str, Any] | None:
    if entry != "personalized":
        return None
    questionnaire = st.session_state.get("pending_questionnaire")
    return questionnaire if isinstance(questionnaire, dict) and questionnaire else None


def _starter_prompts(entry: str) -> list[str]:
    prompt_pool = STARTER_PROMPTS.get(entry) or STARTER_PROMPTS["direct"]
    if (
        st.session_state.get("starter_prompt_entry") != entry
        or not st.session_state.get("starter_prompt_sample")
    ):
        count = min(4, len(prompt_pool))
        st.session_state["starter_prompt_entry"] = entry
        st.session_state["starter_prompt_sample"] = random.sample(prompt_pool, count)
    return list(st.session_state["starter_prompt_sample"])


def _render_welcome(entry: str) -> None:
    config = ENTRY_CONFIG.get(entry, ENTRY_CONFIG["direct"])
    logo = logo_mark_uri()
    title = html.escape(str(config.get("title") or "轻留学 Agent"))
    description = html.escape(str(config.get("description") or "告诉我你的背景和目标，我会先给一版可执行方案。"))
    st.markdown(
        dedent(f"""
        <section class="ql-empty-state">
            <div class="ql-empty-center">
                <span class="ql-empty-logo"><img src="{logo}" alt="轻留学" /></span>
                <h1>{title}</h1>
                <p>{description}</p>
            </div>
        </section>
        """).strip(),
        unsafe_allow_html=True,
    )


def _render_starters(entry: str) -> None:
    st.markdown(
        dedent("""
        <div class="quick-title">可以直接问</div>
        <div class="ql-starter-grid" aria-label="推荐问题">
        """).strip(),
        unsafe_allow_html=True,
    )
    prompts = _starter_prompts(entry)
    for row in range(2):
        cols = st.columns(2, gap="small")
        for col_index, col in enumerate(cols):
            index = row * 2 + col_index
            if index >= len(prompts):
                continue
            prompt = prompts[index]
            with col:
                if st.button(prompt, key=f"starter_{entry}_{index}", use_container_width=True):
                    _queue_chat_request(
                        prompt,
                        entry,
                        requested_agents=_entry_agents(entry),
                        questionnaire=_pending_questionnaire(entry),
                    )
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


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
                    radial-gradient(circle at 50% 18%, rgba(237, 118, 93, 0.08), transparent 34%),
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
                max-width: none !important;
                padding: 8px clamp(32px, 4.8vw, 86px) 124px !important;
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
                width: min(1040px, calc(100% - 72px));
                margin: 0 auto 18px;
            }
            .ql-empty-state {
                min-height: min(56vh, 540px);
                width: min(900px, calc(100% - 80px));
                margin: 0 auto;
                display: grid;
                place-items: center;
                text-align: center;
            }
            .ql-empty-center {
                display: grid;
                justify-items: center;
                gap: 10px;
                padding-top: 44px;
            }
            .ql-empty-logo {
                width: 82px;
                height: 82px;
                display: grid;
                place-items: center;
                margin-bottom: 2px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.74);
                border: 1px solid rgba(234, 217, 210, 0.86);
                box-shadow: 0 16px 34px rgba(73, 42, 33, 0.08);
                overflow: hidden;
            }
            .ql-empty-logo img {
                width: 78px;
                height: 78px;
                object-fit: contain;
                display: block;
            }
            .ql-empty-center h1 {
                margin: 0;
                color: #2b2724;
                font-size: 28px;
                line-height: 1.22;
                font-weight: 930;
                letter-spacing: 0;
            }
            .ql-empty-center p {
                max-width: 560px;
                margin: 0;
                color: #6f625d;
                font-size: 17px;
                line-height: 1.65;
                font-weight: 650;
            }
            .ql-msg-row {
                display: flex;
                gap: 16px;
                align-items: flex-start;
                margin: 18px clamp(20px, 3vw, 56px);
            }
            .ql-msg-row.user {
                justify-content: flex-end;
                margin-left: clamp(36px, 6vw, 96px);
                margin-right: clamp(20px, 3vw, 56px);
            }
            .ql-msg-row.assistant {
                margin-left: clamp(20px, 3vw, 56px);
                margin-right: clamp(36px, 6vw, 96px);
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
                max-width: min(76%, 780px);
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
            .ql-msg-row.thinking {
                align-items: center;
                margin-top: 16px;
            }
            .ql-thinking-inline {
                min-height: 44px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                color: #6f625d;
                font-size: 15px;
                font-weight: 750;
            }
            .ql-thinking-dots {
                display: inline-flex;
                gap: 4px;
                transform: translateY(1px);
            }
            .ql-thinking-dots i {
                width: 4px;
                height: 4px;
                border-radius: 999px;
                background: #b94f3b;
                opacity: 0.35;
                animation: qlThinkingPulse 1.15s infinite ease-in-out;
            }
            .ql-thinking-dots i:nth-child(2) {
                animation-delay: 0.16s;
            }
            .ql-thinking-dots i:nth-child(3) {
                animation-delay: 0.32s;
            }
            @keyframes qlThinkingPulse {
                0%, 80%, 100% {
                    opacity: 0.28;
                    transform: translateY(0);
                }
                40% {
                    opacity: 0.88;
                    transform: translateY(-3px);
                }
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
                width: min(900px, calc(100% - 112px));
                margin: 0 auto 14px;
                color: #7c2f22;
                text-align: center;
                font-size: 15px;
                font-weight: 900;
                opacity: 0.9;
            }
            .ql-starter-grid {
                width: min(900px, calc(100% - 112px));
                margin: 0 auto 24px;
            }
            .main:has(.quick-title) div[data-testid="stHorizontalBlock"] {
                width: min(900px, calc(100% - 112px)) !important;
                margin: 0 auto 16px !important;
                gap: 18px !important;
            }
            .main:has(.quick-title) div[data-testid="stHorizontalBlock"] .stButton button {
                min-height: 76px !important;
                padding: 16px 20px !important;
                justify-content: flex-start !important;
                text-align: center !important;
                white-space: normal !important;
                line-height: 1.5 !important;
                color: #5c514c !important;
                background: rgba(255, 255, 255, 0.70) !important;
                border-radius: 13px !important;
                border-color: rgba(184, 79, 59, 0.28) !important;
                box-shadow: none !important;
                font-size: 15.5px !important;
                font-weight: 780 !important;
            }
            .main:has(.quick-title) div[data-testid="stHorizontalBlock"] .stButton button:hover {
                color: #7c2f22 !important;
                background: rgba(255, 255, 255, 0.94) !important;
                border-color: rgba(184, 79, 59, 0.34) !important;
                box-shadow: 0 12px 26px rgba(73, 42, 33, 0.07) !important;
            }
            [data-testid="stChatInput"] textarea {
                border: 0 !important;
                box-shadow: none !important;
                background: #ffffff !important;
                min-height: 44px !important;
                padding: 12px 4px !important;
                color: #2b2724 !important;
                font-size: 15px !important;
            }
            [data-testid="stChatInput"] {
                max-width: 860px;
                margin: 0 auto;
            }
            [data-testid="stChatInput"] > div {
                min-height: 64px !important;
                border-radius: 20px !important;
                border: 1px solid rgba(206, 194, 187, 0.72) !important;
                background: #ffffff !important;
                box-shadow: 0 16px 42px rgba(73, 42, 33, 0.08);
                padding: 8px 10px 8px 18px !important;
            }
            [data-testid="stChatInput"] > div > div,
            [data-testid="stChatInput"] > div > div > div,
            [data-testid="stChatInput"] div:has(> [data-testid="stChatInputTextArea"]) {
                background: #ffffff !important;
                border-color: transparent !important;
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
                .ql-message-list,
                .ql-empty-state,
                .quick-title,
                .ql-starter-grid,
                .main:has(.quick-title) div[data-testid="stHorizontalBlock"] {
                    width: 100% !important;
                }
                .ql-empty-state {
                    min-height: 46vh;
                }
                .ql-msg-row,
                .ql-msg-row.user,
                .ql-msg-row.assistant {
                    margin-left: 0;
                    margin-right: 0;
                }
                .ql-msg-stack {
                    max-width: 82%;
                }
                .ql-msg-avatar,
                .ql-msg-label {
                    display: none;
                }
                .ql-msg-row.thinking .ql-msg-avatar {
                    display: grid;
                }
                .main:has(.quick-title) div[data-testid="stHorizontalBlock"] .stButton button {
                    min-height: 64px !important;
                    padding: 12px 14px !important;
                    font-size: 14.5px !important;
                }
            }
        </style>
        """).strip()


def render(entry: str = "direct") -> None:
    _ensure_state()
    entry = entry if entry in ENTRY_CONFIG else "direct"
    fresh_requested = st.query_params.get("fresh") == "1"
    if fresh_requested or st.session_state.get("chat_active_entry") not in {None, entry}:
        _reset_chat_view(entry)
        if fresh_requested:
            st.query_params.pop("fresh", None)
            st.rerun()
    else:
        st.session_state["chat_active_entry"] = entry
    if hasattr(st, "html"):
        st.html(_styles())
    else:
        st.markdown(_styles(), unsafe_allow_html=True)
    _render_sidebar(entry)

    st.markdown('<div class="ql-message-list">', unsafe_allow_html=True)
    for message in st.session_state.get("chat_messages", []):
        _render_message(message.get("role", "assistant"), message.get("content", ""))
    if st.session_state.get("pending_chat_request"):
        _render_thinking_message()
    st.markdown("</div>", unsafe_allow_html=True)

    _render_agent_trace()

    if not _has_user_turn() and not st.session_state.get("pending_chat_request"):
        _render_welcome(entry)
        _render_starters(entry)

    if user_input := st.chat_input("告诉我你的 GPA、专业、目标，或继续问我..."):
        _queue_chat_request(
            user_input,
            entry,
            requested_agents=_entry_agents(entry),
            questionnaire=_pending_questionnaire(entry),
        )
        st.rerun()

    _process_pending_chat(entry)
