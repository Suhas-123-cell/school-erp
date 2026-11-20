import json

import groq
import httpx
import pytest

from app.agents import erp_agent
from app.agents.erp_agent import LLMUnavailableError, run_agent
from app.memory import conversation_store as mem
from tests.conftest import FakeGroq, completion, tool_call


def _run(client, message="hi", session_id="s1"):
    return run_agent(message, "S001", session_id, "Arjun Sharma", "10-A", client=client)


def test_plain_answer_without_tools():
    client = FakeGroq([completion("Hello!")])
    result = _run(client)
    assert result.status == "ok"
    assert result.response == "Hello!"
    assert result.intent == "General Query"
    assert result.tool_calls == []
    assert [m["role"] for m in result.new_messages] == ["user", "assistant"]


def test_tool_call_is_dispatched_and_result_fed_back():
    client = FakeGroq([
        completion(tool_calls=[tool_call("get_marks", {"subject": "Mathematics"})]),
        completion("You scored 85 in Mathematics."),
    ])
    result = _run(client, "maths marks?")

    assert result.status == "ok"
    assert result.tools_used == ["get_marks"]
    assert result.intent == "Marks & Grades"
    assert result.tool_calls == [
        {"name": "get_marks", "arguments": {"subject": "Mathematics"}, "status": "ok"}
    ]
    second_request = client.requests[1]["messages"]
    tool_msg = second_request[-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
    assert json.loads(tool_msg["content"])["subject"] == "Mathematics"


def test_parallel_tool_calls_all_run():
    client = FakeGroq([
        completion(tool_calls=[
            tool_call("get_marks", {}, "a"),
            tool_call("get_fees", {}, "b"),
        ]),
        completion("done"),
    ])
    result = _run(client)
    assert result.tools_used == ["get_marks", "get_fees"]
    assert result.intent == "Marks & Grades + Fee Status"
    roles = [m["role"] for m in result.new_messages]
    assert roles == ["user", "assistant", "tool", "tool", "assistant"]


def test_validation_error_is_returned_to_the_model_and_it_can_recover():
    client = FakeGroq([
        completion(tool_calls=[tool_call("get_attendance", {"period": "year", "foo": 1}, "bad")]),
        completion(tool_calls=[tool_call("get_attendance", {"period": "semester"}, "good")]),
        completion("Attendance is fine."),
    ])
    result = _run(client)

    assert result.status == "ok"
    first_tool_msg = client.requests[1]["messages"][-1]
    assert first_tool_msg["tool_call_id"] == "bad"
    assert "Invalid arguments for get_attendance" in json.loads(first_tool_msg["content"])["error"]

    assert [c["status"] for c in result.tool_calls] == ["invalid_arguments", "ok"]
    assert result.tool_calls[0]["error"]
    # only the call that actually ran counts as used
    assert result.tools_used == ["get_attendance"]
    assert result.tool_calls[1]["arguments"] == {"period": "semester"}


def test_unknown_tool_is_reported_not_raised():
    client = FakeGroq([
        completion(tool_calls=[tool_call("drop_tables", {})]),
        completion("Sorry, I can't do that."),
    ])
    result = _run(client)
    assert result.status == "ok"
    assert result.tool_calls[0]["status"] == "unknown_tool"
    assert result.tools_used == []
    assert "Unknown tool" in json.loads(client.requests[1]["messages"][-1]["content"])["error"]


def test_exhausted_loop_is_an_explicit_error_not_a_canned_answer():
    replies = [completion(tool_calls=[tool_call("get_fees", {}, f"c{i}")]) for i in range(10)]
    client = FakeGroq(replies)
    result = _run(client)

    assert result.status == "error"
    assert result.error == "max_iterations_exceeded"
    assert result.response == ""
    assert len(client.requests) == erp_agent.MAX_ITERATIONS
    assert len(result.tool_calls) == erp_agent.MAX_ITERATIONS


def test_empty_model_reply_is_an_error():
    result = _run(FakeGroq([completion(content=None)]))
    assert result.status == "error"
    assert result.error == "empty_model_response"


def test_history_is_replayed_including_earlier_tool_results():
    first = FakeGroq([
        completion(tool_calls=[tool_call("get_fees", {})]),
        completion("You owe some fees."),
    ])
    r1 = _run(first, "fees?", session_id="chat")
    mem.save_turn("chat", "S001", r1.new_messages, r1.intent, r1.tools_used)

    second = FakeGroq([completion("The total was in the earlier result.")])
    _run(second, "what was the annual fee again?", session_id="chat")

    sent = second.requests[0]["messages"]
    roles = [m["role"] for m in sent]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert sent[2]["tool_calls"][0]["function"]["name"] == "get_fees"
    assert "annual_fee" in sent[3]["content"]


def test_request_carries_timeout_and_tool_schemas():
    client = FakeGroq([completion("ok")])
    _run(client)
    req = client.requests[0]
    assert req["timeout"] == erp_agent.REQUEST_TIMEOUT_S
    assert len(req["tools"]) == 10


# --- retries -------------------------------------------------------------

_REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _status_error(cls, code):
    return cls("boom", response=httpx.Response(code, request=_REQ), body=None)


def test_transient_errors_are_retried_with_growing_backoff(no_sleep):
    client = FakeGroq([
        groq.APITimeoutError(request=_REQ),
        _status_error(groq.RateLimitError, 429),
        completion("finally"),
    ])
    result = _run(client)
    assert result.response == "finally"
    assert len(client.requests) == 3
    assert len(no_sleep) == 2
    assert no_sleep[1] > no_sleep[0]


def test_retries_are_bounded(no_sleep):
    errors = [_status_error(groq.InternalServerError, 503) for _ in range(5)]
    client = FakeGroq(errors)
    with pytest.raises(LLMUnavailableError):
        _run(client)
    assert len(client.requests) == erp_agent.MAX_ATTEMPTS
    assert len(no_sleep) == erp_agent.MAX_ATTEMPTS - 1


def test_non_transient_errors_are_not_retried(no_sleep):
    client = FakeGroq([_status_error(groq.AuthenticationError, 401), completion("x")])
    with pytest.raises(LLMUnavailableError):
        _run(client)
    assert len(client.requests) == 1
    assert no_sleep == []


def test_missing_api_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(erp_agent, "_client", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(erp_agent.AgentConfigError):
        erp_agent.get_client()
