# -*- coding: utf-8 -*-
"""Shared UI theme for the Qingliuxue Streamlit frontend."""

from __future__ import annotations

import base64
from pathlib import Path
from textwrap import dedent

import streamlit as st


ASSET_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSET_DIR / "qingliuxue-logo.png"
LOGO_MARK_PATH = ASSET_DIR / "qingliuxue-logo-mark.png"
HOME_IMAGE_PATH = ASSET_DIR / "home-collaboration.png"


@st.cache_data(show_spinner=False)
def image_data_uri(path: Path) -> str:
    mime = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def logo_uri() -> str:
    return image_data_uri(LOGO_PATH)


def logo_mark_uri() -> str:
    return image_data_uri(LOGO_MARK_PATH if LOGO_MARK_PATH.exists() else LOGO_PATH)


def home_image_uri() -> str:
    return image_data_uri(HOME_IMAGE_PATH)


def global_css(hide_sidebar: bool = True) -> str:
    sidebar_hide_css = (
        dedent("""
        [data-testid="stSidebar"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        """).strip()
        if hide_sidebar
        else ""
    )
    return dedent("""
    <style>
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            display: none !important;
        }
    """).strip() + "\n\n" + sidebar_hide_css + "\n\n" + dedent("""

        html,
        body,
        #root,
        .stApp,
        [data-testid="stAppViewContainer"] {
            background: #fff8f5 !important;
        }

        [data-testid="stSkeleton"],
        .stSkeleton,
        div[class*="skeleton"],
        div[class*="Skeleton"],
        div[data-testid*="Skeleton"] {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }

        .block-container {
            max-width: none !important;
            padding: 0 !important;
        }

        iframe {
            display: block;
            width: 100% !important;
        }

        div[data-testid="stVerticalBlock"],
        div[data-testid="stVerticalBlock"] > div {
            gap: 0 !important;
        }
    </style>
    """).strip()


def base_page_css() -> str:
    return dedent("""
    <style>
        :root {
            --coral-900: #7c2f22;
            --coral-800: #9a3d2c;
            --coral-700: #b94f3b;
            --coral-600: #d8614a;
            --coral-500: #ed765d;
            --coral-300: #f6b29f;
            --coral-200: #f8d8cf;
            --coral-100: #fbebe6;
            --coral-050: #fff8f5;
            --ink: #2b2724;
            --muted: #7c716b;
            --line: #ead9d2;
            --card: rgba(255, 252, 250, 0.96);
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            width: 100%;
            margin: 0;
            background: var(--coral-050);
            color: var(--ink);
            font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
        }

        a {
            color: inherit;
            text-decoration: none;
        }

        .ql-page {
            min-height: 100vh;
            background:
                radial-gradient(circle at 50% 16%, rgba(237, 118, 93, 0.12), transparent 32%),
                linear-gradient(180deg, #fff9f6 0%, #fffaf8 48%, #fdf3ee 100%);
        }

        .ql-nav {
            height: 72px;
            background: #f6ded5;
            border-bottom: 1px solid #eac5b9;
            box-shadow: 0 1px 0 rgba(124, 47, 34, 0.04);
        }

        .ql-nav-inner {
            height: 72px;
            width: 100%;
            max-width: none;
            margin: 0;
            padding: 0 38px;
            display: grid;
            grid-template-columns: minmax(260px, 1fr) auto minmax(260px, 1fr);
            align-items: center;
            gap: 42px;
        }

        .ql-brand {
            display: inline-flex;
            align-items: center;
            gap: 12px;
            color: var(--coral-800);
            font-size: 27px;
            font-weight: 900;
            white-space: nowrap;
        }

        .ql-logo-wrap {
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

        .ql-logo {
            width: 54px;
            height: 54px;
            object-fit: contain;
            display: block;
        }

        .ql-links {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 58px;
            color: #6f625d;
            font-size: 19px;
            font-weight: 750;
            white-space: nowrap;
        }

        .ql-links a {
            height: 38px;
            display: inline-flex;
            align-items: center;
            border-bottom: 2px solid transparent;
        }

        .ql-links a.active {
            color: var(--coral-800);
            border-bottom-color: var(--coral-600);
        }

        .ql-nav-right {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 12px;
            min-width: 210px;
        }

        .ql-pill {
            height: 38px;
            padding: 0 18px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            border: 1px solid #e7b9aa;
            color: var(--coral-800);
            background: rgba(255, 255, 255, 0.64);
            font-size: 14px;
            font-weight: 800;
        }

        .ql-auth-link {
            height: 40px;
            padding: 0 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            border: 1px solid #e7b9aa;
            color: var(--coral-800);
            background: rgba(255, 255, 255, 0.64);
            font-size: 15px;
            font-weight: 850;
        }

        .ql-auth-link.primary {
            color: #fff;
            border-color: var(--coral-700);
            background: var(--coral-700);
            box-shadow: 0 14px 26px rgba(184, 79, 59, 0.18);
        }

        .ql-user-pill {
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .ql-main {
            max-width: 1180px;
            margin: 0 auto;
            padding: 64px 24px 88px;
        }

        .ql-section-head {
            text-align: center;
            margin-bottom: 42px;
        }

        .ql-section-head h1 {
            margin: 0;
            color: var(--ink);
            font-size: 44px;
            font-weight: 900;
            line-height: 1.2;
        }

        .ql-section-head p {
            margin: 14px auto 0;
            max-width: 720px;
            color: var(--muted);
            font-size: 17px;
            line-height: 1.75;
            font-weight: 650;
        }

        .ql-grid-2,
        .ql-grid-3 {
            display: grid;
            gap: 28px;
            align-items: stretch;
            justify-content: center;
        }

        .ql-grid-2 {
            grid-template-columns: repeat(2, minmax(320px, 360px));
            max-width: 760px;
            margin: 0 auto;
        }

        .ql-grid-3 {
            grid-template-columns: repeat(3, minmax(320px, 360px));
            max-width: 1120px;
            margin: 0 auto;
        }

        .ql-card {
            width: 100%;
            min-height: 420px;
            padding: 28px 24px;
            border-radius: 20px;
            background: var(--card);
            border: 1px solid var(--line);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }

        .ql-card.featured {
            border-color: var(--line);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
        }

        .ql-card:hover {
            transform: translateY(-6px);
            border-color: #efc4b7;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
        }

        .ql-card-head {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 18px;
        }

        .ql-icon {
            width: 36px;
            height: 36px;
            display: grid;
            place-items: center;
            border-radius: 10px;
            background: #fde8e0;
            color: var(--coral-800);
            font-size: 17px;
            font-weight: 900;
            flex: 0 0 auto;
        }

        .ql-card h2 {
            margin: 0 0 6px;
            color: #2c2c2c;
            font-size: 20px;
            line-height: 1.25;
            font-weight: 850;
        }

        .ql-kicker {
            margin: 0;
            color: #555;
            font-size: 14.5px;
            line-height: 1.65;
            font-weight: 650;
        }

        .ql-list {
            margin: 12px 0 0;
            padding: 0;
            list-style: none;
        }

        .ql-list li {
            display: grid;
            grid-template-columns: 20px 1fr;
            gap: 8px;
            margin: 12px 0;
            color: #555;
            font-size: 14.8px;
            line-height: 1.65;
            font-weight: 650;
        }

        .ql-list li::before {
            content: "";
            width: 8px;
            height: 8px;
            margin-top: 8px;
            border-radius: 50%;
            background: var(--coral-600);
            box-shadow: 0 0 0 5px rgba(237, 118, 93, 0.13);
        }

        .ql-callout {
            margin-top: 18px;
            padding: 13px 14px;
            border-radius: 14px;
            border: 1px solid #efbaa9;
            background: linear-gradient(180deg, #fff3ee 0%, #fde4da 100%);
            color: var(--coral-800);
            text-align: center;
            font-size: 14.8px;
            font-weight: 850;
            line-height: 1.65;
        }

        .ql-spacer {
            flex: 1;
            min-height: 22px;
        }

        .ql-button {
            width: fit-content;
            min-width: 156px;
            height: 44px;
            padding: 0 28px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            align-self: center;
            border-radius: 12px;
            border: 1px solid var(--coral-700);
            color: #ffffff !important;
            background: var(--coral-700);
            box-shadow: 0 16px 32px rgba(184, 79, 59, 0.22);
            font-size: 15px;
            font-weight: 900;
            text-decoration: none !important;
        }

        .ql-button.secondary {
            color: #ffffff !important;
            background: var(--coral-700);
            border-color: var(--coral-700);
            box-shadow: 0 16px 32px rgba(184, 79, 59, 0.22);
        }

        .ql-button:hover {
            transform: translateY(-2px);
        }

        @media (max-width: 960px) {
            .ql-nav-inner {
                padding: 0 20px;
                grid-template-columns: auto auto;
            }

            .ql-links {
                display: none;
            }

            .ql-brand span:last-child {
                font-size: 21px;
            }

            .ql-main {
                padding: 42px 18px 58px;
            }

            .ql-section-head h1 {
                font-size: 31px;
            }

            .ql-grid-2,
            .ql-grid-3 {
                grid-template-columns: 1fr;
                max-width: min(360px, 100%);
            }

            .ql-card {
                min-height: auto;
                padding: 28px 24px;
            }
        }
    </style>
    """).strip()


def nav_html(active: str = "home", user_email: str | None = None) -> str:
    logo = logo_mark_uri()
    items = [
        ("home", "首页", "?page=home"),
        ("school", "智能选校", "?page=school"),
        ("planning", "申请规划", "?page=planning"),
        ("materials", "材料指导", "?page=materials"),
    ]
    links = "\n".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, label, href in items
    )
    if user_email:
        right_html = f"""
                <span class="ql-pill ql-user-pill">{user_email}</span>
                <a class="ql-auth-link" href="?page=logout">退出</a>
        """
    else:
        right_html = """
                <a class="ql-auth-link" href="?page=login">登录</a>
                <a class="ql-auth-link primary" href="?page=register">注册</a>
        """
    return dedent(f"""
    <div class="ql-nav">
        <div class="ql-nav-inner">
            <a class="ql-brand" href="?page=home" aria-label="轻留学">
                <span class="ql-logo-wrap"><img class="ql-logo" src="{logo}" alt="轻留学" /></span>
                <span>轻留学</span>
            </a>
            <nav class="ql-links" aria-label="主导航">
                {links}
            </nav>
            <div class="ql-nav-right">
                {right_html}
            </div>
        </div>
    </div>
    """).strip()


def page_shell(active: str, inner_html: str, user_email: str | None = None) -> str:
    return dedent(f"""
    {base_page_css()}
    <div class="ql-page">
        {nav_html(active, user_email)}
        {inner_html}
    </div>
    """).strip()
