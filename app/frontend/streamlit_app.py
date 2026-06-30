# -*- coding: utf-8 -*-
"""Streamlit frontend for Qingliuxue."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components

FRONTEND_DIR = Path(__file__).resolve().parent
PAGE_ICON = FRONTEND_DIR / "assets" / "qingliuxue-logo-mark.png"

try:
    from api_client import ApiClientError, login_user, register_user
    from ui_theme import base_page_css, global_css, home_image_uri, nav_html, page_shell
except ImportError:  # Allows AppTest/package imports from the project root.
    from app.frontend.api_client import ApiClientError, login_user, register_user
    from app.frontend.ui_theme import base_page_css, global_css, home_image_uri, nav_html, page_shell


st.set_page_config(
    page_title="轻留学 | AI 留学助手",
    page_icon=str(PAGE_ICON),
    layout="wide",
    initial_sidebar_state="expanded",
)

_page_for_css = st.query_params.get("page", "home")
_global_css = global_css(hide_sidebar=_page_for_css != "chat")
if hasattr(st, "html"):
    st.html(_global_css)
else:
    st.markdown(_global_css, unsafe_allow_html=True)


def current_user_email() -> str | None:
    user = st.session_state.get("current_user") or {}
    return user.get("email")


def render_html(html: str, height: int = 920, scrolling: bool = True) -> None:
    html = dedent(html).strip()
    if hasattr(st, "html"):
        st.html(html)
    else:
        components.html(html, height=height, scrolling=scrolling)


def get_page_renderer(module_name: str):
    try:
        module = __import__(module_name, fromlist=["render"])
    except ImportError:
        module = __import__(f"app.frontend.{module_name}", fromlist=["render"])
    return module.render


def render_home() -> None:
    hero_img = home_image_uri()
    inner = dedent(
        f"""
        <main class="ql-main home-main">
            <section class="home-hero">
                <img class="home-hero-image" src="{hero_img}" alt="协作式留学规划" />
            </section>

            <section class="home-copy">
                <h1>轻留学</h1>
                <p class="home-subtitle">AI 与成功同学经验共同铺筑的免费一站式留学服务。</p>
                <div class="home-bullets">
                    <div class="home-bullet" style="--delay: 0ms;">
                        <strong>解决痛点</strong>
                        <span>传统留学中介价格高，很多决策依赖信息差；轻留学把路线、案例、材料和规划透明化。</span>
                    </div>
                    <div class="home-bullet" style="--delay: 120ms;">
                        <strong>降低焦虑</strong>
                        <span>面向中国学生和家长，把国家、专业、预算、就业和风险拆成可比较的路线。</span>
                    </div>
                    <div class="home-bullet" style="--delay: 240ms;">
                        <strong>真实案例</strong>
                        <span>结合优秀同学的申请路径，帮你看到相似背景如何选校、补强和拿到录取。</span>
                    </div>
                    <div class="home-bullet" style="--delay: 360ms;">
                        <strong>一站全包</strong>
                        <span>从画像构建、智能选校、时间线、文书策略、材料准备，到签证和毕业后规划。</span>
                    </div>
                    <div class="home-bullet" style="--delay: 480ms;">
                        <strong>速度更快</strong>
                        <span>无需先约顾问，先用 AI 得到一版可执行方案，再逐步精修。</span>
                    </div>
                </div>
                <a class="ql-button journey-button" href="?page=school">开始留学之旅</a>
            </section>
        </main>

        <style>
            .home-main {{
                max-width: 1320px;
                padding-top: 28px;
            }}

            .home-hero {{
                width: min(1220px, 100%);
                margin: 0 auto 18px;
                display: flex;
                justify-content: center;
                position: relative;
                overflow: hidden;
                border-radius: 26px;
                background: radial-gradient(circle at 50% 55%, rgba(255,255,255,0.86), rgba(255,248,245,0.48) 52%, rgba(255,248,245,0) 74%);
            }}

            .home-hero-image {{
                width: min(1160px, 100%);
                height: clamp(270px, 34vw, 410px);
                object-fit: cover;
                object-position: center;
                border-radius: 26px;
                border: 0;
                box-shadow: none;
                mix-blend-mode: multiply;
                filter: saturate(1.04) contrast(1.02);
                -webkit-mask-image: radial-gradient(ellipse at center, #000 62%, rgba(0,0,0,0.72) 76%, transparent 100%);
                mask-image: radial-gradient(ellipse at center, #000 62%, rgba(0,0,0,0.72) 76%, transparent 100%);
            }}

            .home-copy {{
                width: min(900px, 100%);
                margin: 0 auto;
                text-align: center;
            }}

            .home-copy h1 {{
                margin: 0;
                color: var(--coral-800);
                font-size: 46px;
                font-weight: 950;
                letter-spacing: 0;
            }}

            .home-subtitle {{
                margin: 12px auto 24px;
                color: #5f534e;
                font-size: 18px;
                line-height: 1.7;
                font-weight: 750;
            }}

            .home-bullets {{
                display: grid;
                gap: 12px;
                margin: 0 auto 28px;
                text-align: left;
            }}

            .home-bullet {{
                display: grid;
                grid-template-columns: 116px 1fr;
                gap: 18px;
                align-items: start;
                padding: 16px 18px;
                border-radius: 14px;
                background: rgba(255, 252, 250, 0.9);
                border: 1px solid var(--line);
                box-shadow: 0 16px 36px rgba(73, 42, 33, 0.05);
                opacity: 1;
                transform: none;
            }}

            .home-bullet strong {{
                color: var(--coral-800);
                font-size: 15px;
                font-weight: 900;
            }}

            .home-bullet span {{
                color: #5b514c;
                font-size: 15px;
                line-height: 1.75;
                font-weight: 650;
            }}

            .journey-button {{
                margin: 2px auto 0;
            }}

            @media (max-width: 720px) {{
                .home-bullet {{
                    grid-template-columns: 1fr;
                    gap: 6px;
                }}

                .home-copy h1 {{
                    font-size: 36px;
                }}
            }}
        </style>
        """
    )
    render_html(page_shell("home", inner, current_user_email()), height=980)


def render_school() -> None:
    inner = dedent(
        """
        <main class="ql-main">
            <section class="ql-section-head">
                <h1>智能选校</h1>
                <p>基于你的背景、偏好和真实成功案例，生成一条可执行的留学路线。</p>
            </section>

            <section class="ql-grid-2">
                <article class="ql-card featured">
                    <div class="ql-card-head">
                        <div class="ql-icon">◎</div>
                        <div>
                            <h2>自主选校</h2>
                            <p class="ql-kicker">填写学术背景、能力经历和申请偏好，生成专属路线。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>三步收集学术背景、语言成绩、科研实习和预算偏好。</li>
                        <li>自动拆分冲刺、匹配、保底梯度，减少盲选和焦虑。</li>
                        <li>结合真实案例和长期记忆，给出更贴近你的申请方案。</li>
                        <li>填写项都可以跳过，后续聊天中会继续补全画像。</li>
                    </ul>
                    <div class="ql-callout">完成后进入聊天页，系统会根据你的背景、偏好和真实案例生成个性化路线。</div>
                    <div class="ql-spacer"></div>
                    <a class="ql-button" href="?page=step1">开始填写信息</a>
                </article>

                <article class="ql-card">
                    <div class="ql-card-head">
                        <div class="ql-icon">↗</div>
                        <div>
                            <h2>直接推荐路线</h2>
                            <p class="ql-kicker">不填问卷，先浏览一条真实案例驱动的留学路线。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>快速看到优秀同学如何规划国家、项目和材料主线。</li>
                        <li>适合还没有明确目标，只想先找方向和灵感的用户。</li>
                        <li>进入聊天后可继续追问国家、专业、预算和就业差异。</li>
                        <li>后续会根据对话自动形成你的用户画像。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button secondary" href="?page=chat&entry=direct">直接推荐</a>
                </article>
            </section>
        </main>
        """
    )
    render_html(page_shell("school", inner, current_user_email()), height=900)


def render_planning() -> None:
    inner = dedent(
        """
        <main class="ql-main">
            <section class="ql-section-head">
                <h1>申请规划</h1>
                <p>把留学申请拆成清晰任务：什么时候做、怎么写、方案怎么比。</p>
            </section>

            <section class="ql-grid-3">
                <article class="ql-card featured">
                    <div class="ql-card-head">
                        <div class="ql-icon">⌁</div>
                        <div>
                            <h2>时间线和任务规划</h2>
                            <p class="ql-kicker">把申请季拆成清晰的月份计划和待办任务。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>按国家、阶段、专业拆分准备周期。</li>
                        <li>覆盖考试、选校、推荐信、网申、面试和签证衔接。</li>
                        <li>缺少画像时先给常见路线，再通过聊天补全。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button" href="?page=chat&entry=timeline">生成时间线</a>
                </article>

                <article class="ql-card">
                    <div class="ql-card-head">
                        <div class="ql-icon">✎</div>
                        <div>
                            <h2>文书指导</h2>
                            <p class="ql-kicker">结合你的经历，设计 SOP/PS 主线和素材表达。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>结合文书知识库和真实案例提炼个人主线。</li>
                        <li>区分美国 SOP、英国 PS 等不同写法。</li>
                        <li>提醒中国学生常见误区和素材准备方向。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button secondary" href="?page=chat&entry=essay">生成文书策略</a>
                </article>

                <article class="ql-card">
                    <div class="ql-card-head">
                        <div class="ql-icon">≋</div>
                        <div>
                            <h2>多方案对比</h2>
                            <p class="ql-kicker">把不同国家、专业和项目路线放在同一张表里比较。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>按成本、就业、申请难度、时间成本做矩阵对比。</li>
                        <li>适合比较美国 vs 英国、CS vs DS、冲刺 vs 稳妥。</li>
                        <li>动态信息会提示以官网为准。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button secondary" href="?page=chat&entry=comparison">开始对比</a>
                </article>
            </section>
        </main>
        """
    )
    render_html(page_shell("planning", inner, current_user_email()), height=900)


def render_materials() -> None:
    inner = dedent(
        """
        <main class="ql-main">
            <section class="ql-section-head">
                <h1>材料指导</h1>
                <p>把复杂材料、签证和毕业后规划拆成清单，减少遗漏和返工。</p>
            </section>

            <section class="ql-grid-2">
                <article class="ql-card featured">
                    <div class="ql-card-head">
                        <div class="ql-icon">▤</div>
                        <div>
                            <h2>材料准备</h2>
                            <p class="ql-kicker">生成材料清单、准备顺序和关键质量标准。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>覆盖成绩单、推荐信、简历、文书、语言成绩和作品集。</li>
                        <li>结合材料知识库提醒公章、学校邮箱、认证等细节。</li>
                        <li>按提交前时间窗口给出准备顺序。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button" href="?page=chat&entry=materials">生成材料清单</a>
                </article>

                <article class="ql-card">
                    <div class="ql-card-head">
                        <div class="ql-icon">⌖</div>
                        <div>
                            <h2>签证和毕业后规划</h2>
                            <p class="ql-kicker">规划签证、入学后准备、工签和毕业后发展路径。</p>
                        </div>
                    </div>
                    <ul class="ql-list">
                        <li>按目标国家提示签证类型、资金证明和关键节点。</li>
                        <li>同步考虑毕业后工签、就业准备和长期路径。</li>
                        <li>政策类信息标记为需要官网实时核对。</li>
                    </ul>
                    <div class="ql-spacer"></div>
                    <a class="ql-button secondary" href="?page=chat&entry=visa">查看规划</a>
                </article>
            </section>
        </main>
        """
    )
    render_html(page_shell("materials", inner, current_user_email()), height=860)


def render_auth_frame(title: str, subtitle: str) -> None:
    render_html(
        base_page_css()
        + nav_html("home", current_user_email())
        + f"""
        <style>
            .auth-wrap {{
                max-width: 460px;
                margin: 70px auto 0;
                padding: 34px;
                border-radius: 18px;
                background: rgba(255, 252, 250, 0.96);
                border: 1px solid #ead9d2;
                box-shadow: 0 26px 58px rgba(73, 42, 33, 0.08);
            }}
            .auth-wrap h1 {{
                margin: 0;
                color: #2b2724;
                font-size: 30px;
                font-weight: 950;
            }}
            .auth-wrap p {{
                margin: 10px 0 22px;
                color: #7c716b;
                line-height: 1.7;
                font-weight: 650;
            }}
            .auth-form-host {{
                max-width: 460px;
                margin: -2px auto 0;
                padding: 0 34px 34px;
                border-radius: 0 0 18px 18px;
                background: rgba(255, 252, 250, 0.96);
                border: 1px solid #ead9d2;
                border-top: 0;
                box-shadow: 0 26px 58px rgba(73, 42, 33, 0.08);
            }}
        </style>
        <div class="auth-wrap">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        height=260,
        scrolling=False,
    )


def render_login() -> None:
    render_auth_frame("登录轻留学", "登录后会保留长期画像、历史对话和偏好记忆。")
    with st.container():
        st.markdown('<div class="auth-form-host">', unsafe_allow_html=True)
        with st.form("login_form"):
            email = st.text_input("邮箱")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    if submitted:
        try:
            response = login_user(email, password)
        except ApiClientError as exc:
            st.error(str(exc))
            st.caption("如果后端还没启动，请先运行：uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000")
            return
        st.session_state["access_token"] = response["access_token"]
        st.session_state["current_user"] = response["user"]
        st.session_state["chat_messages"] = []
        st.session_state["conversation_id"] = None
        st.query_params["page"] = "home"
        st.rerun()


def render_register() -> None:
    render_auth_frame("注册轻留学", "注册只需要邮箱和密码；功能和访客一致，但会保存长期记忆。")
    with st.container():
        st.markdown('<div class="auth-form-host">', unsafe_allow_html=True)
        with st.form("register_form"):
            email = st.text_input("邮箱")
            display_name = st.text_input("昵称（可选）")
            password = st.text_input("密码", type="password")
            password2 = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册并登录", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    if submitted:
        if password != password2:
            st.error("两次输入的密码不一致")
            return
        try:
            response = register_user(email, password, display_name or None)
        except ApiClientError as exc:
            st.error(str(exc))
            st.caption("如果后端还没启动，请先运行：uvicorn app.backend.api.main:app --host 0.0.0.0 --port 8000")
            return
        st.session_state["access_token"] = response["access_token"]
        st.session_state["current_user"] = response["user"]
        st.session_state["chat_messages"] = []
        st.session_state["conversation_id"] = None
        st.query_params["page"] = "home"
        st.rerun()


def logout() -> None:
    for key in ["access_token", "current_user", "chat_messages", "conversation_id", "last_route", "last_agent_results"]:
        st.session_state.pop(key, None)
    st.query_params["page"] = "home"
    st.rerun()


page = st.query_params.get("page", "home")

if page == "home":
    render_home()
elif page == "school":
    render_school()
elif page == "planning":
    render_planning()
elif page == "materials":
    render_materials()
elif page == "login":
    render_login()
elif page == "register":
    render_register()
elif page == "logout":
    logout()
elif page == "step1":
    get_page_renderer("school_step1")()
elif page == "step2":
    get_page_renderer("school_step2")()
elif page == "step3":
    get_page_renderer("school_step3")()
elif page == "chat":
    get_page_renderer("chat_page")(st.query_params.get("entry", "direct"))
else:
    render_home()
