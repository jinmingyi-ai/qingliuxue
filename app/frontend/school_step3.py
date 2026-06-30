# -*- coding: utf-8 -*-
"""Questionnaire step 3: application preferences."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from textwrap import dedent

PAGE_ICON = Path(__file__).resolve().parent / "assets" / "qingliuxue-logo-mark.png"

try:
    from ui_theme import base_page_css, nav_html
except ImportError:  # Allows importing as app.frontend.school_step3 in tests.
    from app.frontend.ui_theme import base_page_css, nav_html


def _user_email() -> str | None:
    user = st.session_state.get("current_user") or {}
    return user.get("email")


def _ensure_questionnaire() -> dict:
    st.session_state.setdefault("questionnaire", {})
    return st.session_state["questionnaire"]


def _go(page: str) -> None:
    st.query_params["page"] = page
    st.rerun()


def _html(html: str, height: int = 260) -> None:
    html = dedent(html).strip()
    if hasattr(st, "html"):
        st.html(html)
    else:
        components.html(html, height=height, scrolling=False)


def _chrome() -> None:
    _html(
        base_page_css()
        + nav_html("school", _user_email())
        + """
        <style>
            .main .block-container { max-width: 920px !important; padding: 42px 24px 80px !important; }
            .wizard-head { text-align: center; margin-bottom: 28px; }
            .wizard-head h1 { margin: 0; font-size: 34px; font-weight: 950; color: #2b2724; }
            .wizard-head p { margin: 10px 0 0; color: #7c716b; font-weight: 650; }
            .stepper { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 34px; }
            .step-pill { min-height: 58px; padding: 12px; border-radius: 14px; border: 1px solid #ead9d2; background: rgba(255, 252, 250, 0.85); color: #7c716b; text-align: center; font-weight: 850; }
            .step-pill.active { color: #fff; background: #b94f3b; border-color: #b94f3b; box-shadow: 0 16px 32px rgba(184, 79, 59, 0.18); }
            .step-pill.done { color: #9a3d2c; background: #fde8e0; border-color: #efbaa9; }
            .form-card { padding: 34px; border-radius: 18px; background: rgba(255, 252, 250, 0.96); border: 1px solid #ead9d2; box-shadow: 0 26px 58px rgba(73, 42, 33, 0.08); }
            .form-card h2 { margin: 0 0 18px; text-align: center; font-size: 26px; font-weight: 950; }
            .stButton button, .stFormSubmitButton button { border-radius: 10px !important; font-weight: 900 !important; }
            .stFormSubmitButton button { border-color: #b94f3b !important; background: #b94f3b !important; color: white !important; }
        </style>
        <div class="wizard-head">
            <h1>智能选校</h1>
            <p>最后收集国家、专业、预算和你看重的因素；也可以直接生成推荐。</p>
        </div>
        <div class="stepper">
            <div class="step-pill done">1<br/>学术背景</div>
            <div class="step-pill done">2<br/>申请能力/背景</div>
            <div class="step-pill active">3<br/>申请偏好</div>
        </div>
        """,
        height=260,
    )


def render() -> None:
    q = _ensure_questionnaire()
    _chrome()
    st.markdown('<div class="form-card"><h2>申请偏好</h2>', unsafe_allow_html=True)
    with st.form("step3_form"):
        target_countries = st.multiselect(
            "想申请的国家/地区",
            ["美国", "英国", "加拿大", "澳大利亚", "新加坡", "香港", "澳门", "暂不确定"],
            default=q.get("target_countries", []),
        )
        target_majors = st.multiselect(
            "感兴趣的硕士专业方向",
            ["商科", "金融/金工", "计算机/数据/AI", "工程", "文社科/公共管理", "教育", "设计/艺术", "医学/生物相关", "暂不确定"],
            default=q.get("target_majors", []),
        )
        budget = st.multiselect(
            "留学预算范围",
            ["25 万以内", "25-35 万", "35-50 万", "50-70 万", "70 万以上", "暂不确定"],
            default=q.get("budget", []),
        )
        priorities = st.multiselect(
            "你更看重什么",
            ["学校排名", "专业实力", "就业结果", "留在当地工作的可能性", "性价比", "综合平衡"],
            default=q.get("priorities", []),
        )
        extra_notes = st.text_area(
            "其他希望补充的信息",
            value=q.get("extra_notes", ""),
            placeholder="例如：双非一本金融，GPA 3.4，想申请新加坡商科，也想看英国方案。",
        )
        col_prev, col_submit = st.columns(2)
        with col_prev:
            prev = st.form_submit_button("上一步", use_container_width=True)
        with col_submit:
            submitted = st.form_submit_button("生成推荐", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    q.update(
        {
            "target_countries": target_countries,
            "target_majors": target_majors,
            "budget": budget,
            "priorities": priorities,
            "extra_notes": extra_notes,
        }
    )

    if prev:
        _go("step2")
    if submitted:
        st.session_state["pending_questionnaire"] = dict(q)
        st.session_state["chat_messages"] = []
        st.session_state["conversation_id"] = None
        st.query_params["page"] = "chat"
        st.query_params["entry"] = "personalized"
        st.query_params["fresh"] = "1"
        st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="轻留学 | 申请偏好", page_icon=str(PAGE_ICON), layout="wide")
    render()
