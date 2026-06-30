import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path("logs/conversations.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                student_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                tools_used TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON conversations(session_id)")
        conn.commit()


def save_message(
    session_id: str,
    student_id: str,
    role: str,
    content: str,
    intent: Optional[str] = None,
    tools_used: Optional[List[str]] = None,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO conversations
               (session_id, student_id, role, content, intent, tools_used, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                student_id,
                role,
                content,
                intent,
                json.dumps(tools_used) if tools_used else None,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_openai_messages(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    history = get_history(session_id, limit=limit * 2)
    return [
        {"role": r["role"], "content": r["content"]}
        for r in history
        if r["role"] in ("user", "assistant")
    ]


def get_all_sessions(student_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with _get_conn() as conn:
        if student_id:
            rows = conn.execute(
                """SELECT session_id, student_id, COUNT(*) as msg_count,
                          MIN(created_at) as started_at, MAX(created_at) as last_at
                   FROM conversations WHERE student_id = ?
                   GROUP BY session_id ORDER BY last_at DESC""",
                (student_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT session_id, student_id, COUNT(*) as msg_count,
                          MIN(created_at) as started_at, MAX(created_at) as last_at
                   FROM conversations
                   GROUP BY session_id ORDER BY last_at DESC"""
            ).fetchall()
    return [dict(r) for r in rows]


def generate_session_id() -> str:
    return str(uuid.uuid4())
