# -*- coding: utf-8 -*-
"""Questionnaire step 2: application readiness."""

from __future__ import annotations

import streamlit as st

from ui_theme import base_page_css, nav_html


def _user_email() -> str | None:
    user = st.session_state.get("current_user") or {}
    return user.get("email")


def _ensure_questionnaire() -> dict:
    st.session_state.setdefault("questionnaire", {})
    return st.session_state["questionnaire"]


def _go(page: str) -> None:
    st.query_params["page"] = page
    st.rerun()


def _chrome() -> None:
    st.markdown(
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
            <p>第二步收集语言、经历和入学年份；可以整页留空。</p>
        </div>
        <div class="stepper">
            <div class="step-pill done">1<br/>学术背景</div>
            <div class="step-pill active">2<br/>申请能力/背景</div>
            <div class="step-pill">3<br/>申请偏好</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:
    q = _ensure_questionnaire()
    _chrome()
    st.markdown('<div class="form-card"><h2>申请能力/背景</h2>', unsafe_allow_html=True)
    with st.form("step2_form"):
        col1, col2 = st.columns(2)
        with col1:
            language_type = st.selectbox("语言/标化类型", ["", "IELTS", "TOEFL", "GRE", "GMAT", "暂未考试"], index=0)
        with col2:
            language_score = st.text_input("分数或备注", value=q.get("language_score", ""))
        experiences = st.multiselect(
            "你具备哪些经历",
            ["实习", "科研项目", "比赛/竞赛", "奖项", "发表论文", "志愿活动", "工作经历", "产品/项目落地", "暂时没有"],
            default=q.get("experiences", []),
        )
        application_year = st.selectbox("计划入学年份", ["", "2026", "2027", "2028 及以后"], index=0)
        col_prev, col_next = st.columns(2)
        with col_prev:
            prev = st.form_submit_button("上一步", use_container_width=True)
        with col_next:
            submitted = st.form_submit_button("下一步", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if prev:
        q.update(
            {
                "language_type": language_type,
                "language_score": language_score,
                "experiences": experiences,
                "application_year": application_year,
            }
        )
        _go("step1")
    if submitted:
        q.update(
            {
                "language_type": language_type,
                "language_score": language_score,
                "experiences": experiences,
                "application_year": application_year,
            }
        )
        _go("step3")


if __name__ == "__main__":
    st.set_page_config(page_title="轻留学 | 申请能力", page_icon="🎓", layout="wide")
    render()

