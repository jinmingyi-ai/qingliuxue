# -*- coding: utf-8 -*-
"""Questionnaire step 1: academic background."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from textwrap import dedent

try:
    from ui_theme import base_page_css, nav_html
except ImportError:  # Allows importing as app.frontend.school_step1 in tests.
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


def _chrome(step: int) -> None:
    _html(
        base_page_css()
        + nav_html("school", _user_email())
        + f"""
        <style>
            .main .block-container {{
                max-width: 920px !important;
                padding: 42px 24px 80px !important;
            }}
            .wizard-head {{ text-align: center; margin-bottom: 28px; }}
            .wizard-head h1 {{ margin: 0; font-size: 34px; font-weight: 950; color: #2b2724; }}
            .wizard-head p {{ margin: 10px 0 0; color: #7c716b; font-weight: 650; }}
            .stepper {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
                margin: 0 0 34px;
            }}
            .step-pill {{
                min-height: 58px;
                padding: 12px;
                border-radius: 14px;
                border: 1px solid #ead9d2;
                background: rgba(255, 252, 250, 0.85);
                color: #7c716b;
                text-align: center;
                font-weight: 850;
            }}
            .step-pill.active {{
                color: #fff;
                background: #b94f3b;
                border-color: #b94f3b;
                box-shadow: 0 16px 32px rgba(184, 79, 59, 0.18);
            }}
            .step-pill.done {{
                color: #9a3d2c;
                background: #fde8e0;
                border-color: #efbaa9;
            }}
            .form-card {{
                padding: 34px;
                border-radius: 18px;
                background: rgba(255, 252, 250, 0.96);
                border: 1px solid #ead9d2;
                box-shadow: 0 26px 58px rgba(73, 42, 33, 0.08);
            }}
            .form-card h2 {{ margin: 0 0 18px; text-align: center; font-size: 26px; font-weight: 950; }}
            .stButton button, .stFormSubmitButton button {{
                border-radius: 10px !important;
                border-color: #b94f3b !important;
                background: #b94f3b !important;
                color: white !important;
                font-weight: 900 !important;
            }}
        </style>
        <div class="wizard-head">
            <h1>智能选校</h1>
            <p>根据你的个人背景生成个性化 AI 留学方案，所有问题都可以留空。</p>
        </div>
        <div class="stepper">
            <div class="step-pill {'active' if step == 1 else 'done'}">1<br/>学术背景</div>
            <div class="step-pill {'active' if step == 2 else ''}">2<br/>申请能力/背景</div>
            <div class="step-pill {'active' if step == 3 else ''}">3<br/>申请偏好</div>
        </div>
        """,
        height=260,
    )


def render() -> None:
    q = _ensure_questionnaire()
    _chrome(1)
    st.markdown('<div class="form-card"><h2>学术背景</h2>', unsafe_allow_html=True)
    with st.form("step1_form"):
        current_level = st.selectbox(
            "当前最高学历",
            ["", "本科在读", "本科毕业", "硕士在读（申请第二硕士）", "硕士毕业", "其他"],
            index=["", "本科在读", "本科毕业", "硕士在读（申请第二硕士）", "硕士毕业", "其他"].index(q.get("current_level", "")) if q.get("current_level", "") in ["", "本科在读", "本科毕业", "硕士在读（申请第二硕士）", "硕士毕业", "其他"] else 0,
        )
        undergraduate_school = st.text_input("本科/当前院校名称", value=q.get("undergraduate_school", ""))
        undergraduate_major = st.text_input("本科/当前专业名称", value=q.get("undergraduate_major", ""))
        col1, col2 = st.columns(2)
        with col1:
            score_type = st.selectbox("成绩类型", ["", "绩点（4.0 制）", "均分（百分制）"], index=0)
        with col2:
            score_value = st.text_input("成绩数值", value=q.get("score_value", ""))
        submitted = st.form_submit_button("下一步", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        q.update(
            {
                "current_level": current_level,
                "undergraduate_school": undergraduate_school,
                "undergraduate_major": undergraduate_major,
                "score_type": score_type,
                "score_value": score_value,
            }
        )
        _go("step2")


if __name__ == "__main__":
    st.set_page_config(page_title="轻留学 | 学术背景", page_icon="🎓", layout="wide")
    render()
