import json
import shutil
from types import SimpleNamespace

import pytest

from app.memory import conversation_store as mem
from app.paths import MOCK_DATA_DIR


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own empty conversation database."""
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "conversations.db")
    mem.init_db()


@pytest.fixture
def no_sleep(monkeypatch):
    from app.agents import erp_agent

    delays = []
    monkeypatch.setattr(erp_agent.time, "sleep", delays.append)
    return delays


def tool_call(name, arguments, call_id="call_1"):
    args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=args))


def completion(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeGroq:
    """Stands in for the Groq client. Replays scripted replies and records requests."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Snapshot: the agent keeps appending to the same list between calls.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def students_file(tmp_path, monkeypatch):
    """A writable copy of students.json for tests that modify it."""
    from app.api import students

    path = tmp_path / "students.json"
    shutil.copy(MOCK_DATA_DIR / "students.json", path)
    monkeypatch.setattr(students, "DATA_PATH", path)
    return path
