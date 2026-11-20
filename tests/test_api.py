import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from app.agents import erp_agent
from app.main import app
from app.memory import conversation_store as mem
from tests.conftest import FakeGroq, completion, tool_call


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def use_llm(monkeypatch):
    def install(replies):
        fake = FakeGroq(replies)
        monkeypatch.setattr(erp_agent, "get_client", lambda: fake)
        return fake
    return install


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_chat_with_tool_call(client, use_llm):
    use_llm([
        completion(tool_calls=[tool_call("get_marks", {"subject": "Mathematics"})]),
        completion("You scored 85 in Mathematics."),
    ])
    r = client.post("/chat", json={"message": "maths marks", "student_id": "S001"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Fetched"
    assert body["intent"] == "Marks & Grades"
    assert body["response"] == "You scored 85 in Mathematics."
    assert body["tools_used"] == ["get_marks"]
    assert body["tool_calls"] == [
        {"name": "get_marks", "arguments": {"subject": "Mathematics"}, "status": "ok", "error": None}
    ]
    assert "execution_plan" not in body
    assert body["session_id"]


def test_second_turn_sees_the_first_turns_tool_result(client, use_llm):
    fake = use_llm([
        completion(tool_calls=[tool_call("get_fees", {})]),
        completion("Fees pending."),
        completion("As fetched earlier."),
    ])
    sid = client.post("/chat", json={"message": "fees?"}).json()["session_id"]
    client.post("/chat", json={"message": "and the annual amount?", "session_id": sid})

    third_request = fake.requests[2]["messages"]
    assert any(m["role"] == "tool" and "annual_fee" in m["content"] for m in third_request)


def test_history_endpoint_hides_tool_messages(client, use_llm):
    use_llm([
        completion(tool_calls=[tool_call("get_fees", {})]),
        completion("Fees pending."),
    ])
    sid = client.post("/chat", json={"message": "fees?"}).json()["session_id"]

    r = client.get("/chat/history", params={"session_id": sid})
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["tools_used"] == ["get_fees"]

    sessions = client.get("/chat/sessions", params={"student_id": "S001"}).json()
    assert sessions["sessions"][0]["msg_count"] == 2


def test_hallucinated_args_do_not_cause_a_500(client, use_llm):
    use_llm([
        completion(tool_calls=[tool_call("get_fees", {"student_name": "Arjun"})]),
        completion(tool_calls=[tool_call("get_fees", {})]),
        completion("Here are your fees."),
    ])
    r = client.post("/chat", json={"message": "fees"})
    assert r.status_code == 200
    statuses = [c["status"] for c in r.json()["tool_calls"]]
    assert statuses == ["invalid_arguments", "ok"]


def test_exhausted_loop_returns_error_status_and_is_not_stored(client, use_llm):
    use_llm([completion(tool_calls=[tool_call("get_fees", {}, f"c{i}")]) for i in range(10)])
    r = client.post("/chat", json={"message": "fees", "session_id": "looping"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["error"] == "max_iterations_exceeded"
    assert body["response"] == ""
    assert len(body["tool_calls"]) == erp_agent.MAX_ITERATIONS
    assert mem.get_conversation_messages("looping") == []


def test_llm_outage_maps_to_502(client, monkeypatch, no_sleep):
    import groq
    import httpx

    req = httpx.Request("POST", "https://api.groq.com")
    fake = FakeGroq([groq.APIConnectionError(request=req)] * 3)
    monkeypatch.setattr(erp_agent, "get_client", lambda: fake)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 502


def test_missing_api_key_maps_to_503(client, monkeypatch):
    monkeypatch.setattr(erp_agent, "_client", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 503
    assert "GROQ_API_KEY" in r.json()["detail"]


def test_blank_message_is_rejected(client):
    assert client.post("/chat", json={"message": "   "}).status_code == 400
    assert client.post("/chat", json={"message": ""}).status_code == 422


def test_unknown_student_is_404(client, use_llm):
    use_llm([])
    r = client.post("/chat", json={"message": "hi", "student_id": "S999"})
    assert r.status_code == 404


def test_history_requires_an_identifier_and_404s_on_unknown(client):
    assert client.get("/chat/history").status_code == 400
    assert client.get("/chat/history", params={"session_id": "nope"}).status_code == 404


def test_delete_history(client, use_llm):
    use_llm([completion("hello")])
    sid = client.post("/chat", json={"message": "hi"}).json()["session_id"]
    assert client.delete("/chat/history", params={"session_id": sid}).json()["deleted"] == 2
    assert client.delete("/chat/history", params={"session_id": sid}).status_code == 404


def test_slow_agent_does_not_block_the_event_loop(client, monkeypatch):
    """While the sync agent runs, other requests on the same loop still get served."""
    release = threading.Event()
    entered = threading.Event()
    released_in_time = []

    def slow_agent(**kwargs):
        entered.set()
        # Only set by the test after /health has been answered. If the agent
        # blocked the loop, /health could not be served and this times out.
        released_in_time.append(release.wait(timeout=2))
        return erp_agent.AgentResult("late", "ok", "General Query", [], [], [])

    monkeypatch.setattr("app.api.chat.run_agent", slow_agent)

    import httpx

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            slow = asyncio.create_task(ac.post("/chat", json={"message": "hi"}))
            while not entered.is_set():
                await asyncio.sleep(0.01)
            health = await ac.get("/health")
            release.set()
            return health.status_code, (await slow).status_code

    assert asyncio.run(scenario()) == (200, 200)
    assert released_in_time == [True]


def test_students_crud(client, students_file):
    assert len(client.get("/students").json()) == 4
    created = client.post("/students", json={
        "name": "Test Kid", "student_class": "10-A", "roll_number": 40, "section": "A",
        "gender": "F", "dob": "2010-01-01", "parent": "Parent",
    })
    assert created.status_code == 201
    sid = created.json()["student_id"]
    assert sid == "S005"
    assert client.delete(f"/students/{sid}").status_code == 204
    assert client.delete(f"/students/{sid}").status_code == 404


def test_paths_do_not_depend_on_cwd(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert client.get("/").status_code == 200
    assert client.get("/students").status_code == 200
