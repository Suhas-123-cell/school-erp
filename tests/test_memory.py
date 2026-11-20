from app.memory import conversation_store as mem


def _turn(question, tool_payload="x" * 40, call_id="c1"):
    return [
        {"role": "user", "content": question},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": "get_fees", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": call_id, "content": tool_payload},
        {"role": "assistant", "content": f"answer to {question}"},
    ]


def test_tool_calls_and_results_round_trip():
    mem.save_turn("s", "S001", _turn("q1"), intent="Fee Status", tools_used=["get_fees"])
    msgs = mem.get_conversation_messages("s")

    assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant"]
    assert msgs[1]["content"] is None
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "get_fees"
    assert msgs[2]["tool_call_id"] == "c1"
    assert msgs[2]["content"] == "x" * 40


def test_history_endpoint_view_hides_tool_plumbing():
    mem.save_turn("s", "S001", _turn("q1"), intent="Fee Status", tools_used=["get_fees"])
    visible = mem.get_history("s")
    assert [m["role"] for m in visible] == ["user", "assistant"]
    assert visible[1]["intent"] == "Fee Status"
    assert mem.get_all_sessions("S001")[0]["msg_count"] == 2


def test_plain_save_message_still_works():
    mem.save_message("s", "S001", "user", "hello")
    mem.save_message("s", "S001", "assistant", "hi", intent="General Query")
    assert [m["role"] for m in mem.get_conversation_messages("s")] == ["user", "assistant"]


def test_trimming_drops_oldest_turns_first():
    for i in range(4):
        mem.save_turn("s", "S001", _turn(f"q{i}", tool_payload="y" * 400, call_id=f"c{i}"))
    one_turn = sum(mem.estimate_tokens(m) for m in _turn("q0", "y" * 400))

    kept = mem.get_conversation_messages("s", token_budget=one_turn * 2 + 1)
    users = [m["content"] for m in kept if m["role"] == "user"]
    assert users == ["q2", "q3"]


def test_trimming_never_splits_a_tool_call_from_its_result():
    for i in range(6):
        mem.save_turn("s", "S001", _turn(f"q{i}", tool_payload="z" * (50 + 37 * i), call_id=f"c{i}"))

    for budget in range(0, 700, 7):
        kept = mem.get_conversation_messages("s", token_budget=budget)
        if kept:
            assert kept[0]["role"] == "user"
        pending = set()
        for m in kept:
            if m.get("tool_calls"):
                pending = {c["id"] for c in m["tool_calls"]}
            elif m["role"] == "tool":
                assert m["tool_call_id"] in pending
                pending.discard(m["tool_call_id"])
            elif m["role"] == "assistant":
                assert not pending
        assert not pending


def test_budget_smaller_than_latest_turn_returns_nothing():
    mem.save_turn("s", "S001", _turn("q", tool_payload="w" * 4000))
    assert mem.get_conversation_messages("s", token_budget=100) == []


def test_default_budget_is_applied():
    for i in range(30):
        mem.save_turn("s", "S001", _turn(f"q{i}", tool_payload="p" * 2000, call_id=f"c{i}"))
    kept = mem.get_conversation_messages("s")
    assert 0 < len(kept) < 30 * 4
    assert sum(mem.estimate_tokens(m) for m in kept) <= mem.HISTORY_TOKEN_BUDGET
    assert kept[-1]["content"] == "answer to q29"


def test_sessions_are_isolated_and_deletable():
    mem.save_turn("a", "S001", _turn("qa"))
    mem.save_turn("b", "S002", _turn("qb"))
    assert [m["content"] for m in mem.get_conversation_messages("a") if m["role"] == "user"] == ["qa"]
    assert mem.delete_session("a") == 4
    assert mem.get_conversation_messages("a") == []
    assert mem.get_conversation_messages("b")


def test_init_db_upgrades_an_old_schema(tmp_path, monkeypatch):
    import sqlite3

    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("""CREATE TABLE conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, student_id TEXT NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT, tools_used TEXT, created_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO conversations (session_id, student_id, role, content, created_at) "
                 "VALUES ('s','S001','user','old question','2026-01-01')")
    conn.execute("INSERT INTO conversations (session_id, student_id, role, content, created_at) "
                 "VALUES ('s','S001','assistant','old answer','2026-01-01')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(mem, "DB_PATH", old)
    mem.init_db()
    mem.init_db()  # idempotent
    msgs = mem.get_conversation_messages("s")
    assert [m["content"] for m in msgs] == ["old question", "old answer"]
    assert len(mem.get_history("s")) == 2
