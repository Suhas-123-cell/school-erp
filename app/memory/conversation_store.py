import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.paths import DB_PATH

# Approximate token budget for the history sent to the model on each turn.
HISTORY_TOKEN_BUDGET = int(os.getenv("HISTORY_TOKEN_BUDGET", "4000"))
# Rows read from the database before budget trimming is applied.
_MAX_ROWS_SCANNED = 400

# Rows with is_internal=1 (assistant tool calls and tool results) are replayed to
# the model but hidden from the history endpoints.
_VISIBLE = "is_internal = 0"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_get_conn()) as conn:
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
        # Columns added after the first version; upgrade existing databases in place.
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
        for column, ddl in (
            ("tool_calls", "TEXT"),
            ("tool_call_id", "TEXT"),
            ("is_internal", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE conversations ADD COLUMN {column} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON conversations(session_id)")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert(
    conn: sqlite3.Connection,
    session_id: str,
    student_id: str,
    message: Dict[str, Any],
    intent: Optional[str] = None,
    tools_used: Optional[List[str]] = None,
) -> None:
    tool_calls = message.get("tool_calls")
    is_internal = 1 if (tool_calls or message["role"] == "tool") else 0
    conn.execute(
        """INSERT INTO conversations
           (session_id, student_id, role, content, intent, tools_used, created_at,
            tool_calls, tool_call_id, is_internal)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            student_id,
            message["role"],
            message.get("content") or "",
            intent,
            json.dumps(tools_used) if tools_used else None,
            _now(),
            json.dumps(tool_calls) if tool_calls else None,
            message.get("tool_call_id"),
            is_internal,
        ),
    )


def save_message(
    session_id: str,
    student_id: str,
    role: str,
    content: str,
    intent: Optional[str] = None,
    tools_used: Optional[List[str]] = None,
) -> None:
    with closing(_get_conn()) as conn:
        _insert(conn, session_id, student_id, {"role": role, "content": content}, intent, tools_used)
        conn.commit()


def save_turn(
    session_id: str,
    student_id: str,
    messages: List[Dict[str, Any]],
    intent: Optional[str] = None,
    tools_used: Optional[List[str]] = None,
) -> None:
    """Persist one full turn (user, assistant tool calls, tool results, final answer).

    Written in a single transaction so a turn is stored completely or not at all;
    that keeps tool-call/result pairs intact when history is replayed.
    intent and tools_used are attached to the last message (the final answer).
    """
    with closing(_get_conn()) as conn:
        last = len(messages) - 1
        for i, message in enumerate(messages):
            is_last = i == last
            _insert(
                conn, session_id, student_id, message,
                intent if is_last else None,
                tools_used if is_last else None,
            )
        conn.commit()


def estimate_tokens(message: Dict[str, Any]) -> int:
    """Rough token count (about 4 characters per token) including tool-call payloads."""
    text = message.get("content") or ""
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        text += fn.get("name", "") + fn.get("arguments", "")
    return len(text) // 4 + 4


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"role": row["role"], "content": row["content"]}
    if row["tool_calls"]:
        msg["tool_calls"] = json.loads(row["tool_calls"])
        if not msg["content"]:
            msg["content"] = None
    if row["role"] == "tool":
        msg["tool_call_id"] = row["tool_call_id"]
    return msg


def get_conversation_messages(
    session_id: str, token_budget: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Return stored messages in OpenAI chat format, trimmed to a token budget.

    Trimming drops whole turns (a user message and everything that followed it
    up to the next user message), oldest first. Splitting inside a turn could
    leave a tool result without the assistant tool call that produced it, which
    the API rejects.
    """
    budget = HISTORY_TOKEN_BUDGET if token_budget is None else token_budget
    with closing(_get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, _MAX_ROWS_SCANNED),
        ).fetchall()
    messages = [_row_to_message(r) for r in reversed(rows)]

    turns: List[List[Dict[str, Any]]] = []
    for m in messages:
        if m["role"] == "user" or not turns:
            turns.append([])
        turns[-1].append(m)
    # A scan window can start mid-turn; such a partial first turn has no user message.
    if turns and turns[0][0]["role"] != "user":
        turns.pop(0)

    kept: List[List[Dict[str, Any]]] = []
    used = 0
    for turn in reversed(turns):
        cost = sum(estimate_tokens(m) for m in turn)
        if used + cost > budget:
            break
        kept.append(turn)
        used += cost
    return [m for turn in reversed(kept) for m in turn]


def get_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """User-visible messages only (no tool-call plumbing)."""
    with closing(_get_conn()) as conn:
        rows = conn.execute(
            f"SELECT * FROM conversations WHERE session_id = ? AND {_VISIBLE} "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_all_sessions(student_id: Optional[str] = None) -> List[Dict[str, Any]]:
    preview_sql = f"""(SELECT content FROM conversations
                        WHERE session_id = c.session_id AND role = 'user'
                        AND {_VISIBLE}
                        ORDER BY id ASC LIMIT 1) as first_message"""
    where = f"c.{_VISIBLE}"
    params: tuple = ()
    if student_id:
        where += " AND c.student_id = ?"
        params = (student_id,)
    with closing(_get_conn()) as conn:
        rows = conn.execute(
            f"""SELECT c.session_id, c.student_id, COUNT(*) as msg_count,
                      MIN(c.created_at) as started_at, MAX(c.created_at) as last_at,
                      {preview_sql}
               FROM conversations c WHERE {where}
               GROUP BY c.session_id ORDER BY last_at DESC LIMIT 30""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: str) -> int:
    with closing(_get_conn()) as conn:
        cur = conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount


def generate_session_id() -> str:
    return str(uuid.uuid4())
