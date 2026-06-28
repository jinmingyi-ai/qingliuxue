# -*- coding: utf-8 -*-
"""Small SQLite user store for the demo authentication system."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "app" / "data" / "auth" / "qingliuxue.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def database_path() -> Path:
    url = os.getenv("DATABASE_URL")
    if url and url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return DEFAULT_DB_PATH


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"] or row["email"].split("@", 1)[0],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_user(email: str, password_hash: str, display_name: str | None = None) -> dict[str, Any]:
    init_db()
    user_id = "usr_" + uuid.uuid4().hex[:16]
    now = _now()
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, password_hash, display_name, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("这个邮箱已经注册过了") from exc
    user = get_user_by_id(user_id)
    if not user:
        raise RuntimeError("用户创建失败")
    return user


def get_user_by_email(email: str, include_password: bool = False) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    user = _row_to_user(row)
    if user and include_password:
        user["password_hash"] = row["password_hash"]
    return user


def get_user_by_id(user_id: str, include_password: bool = False) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    user = _row_to_user(row)
    if user and include_password:
        user["password_hash"] = row["password_hash"]
    return user

