import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import groq
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

from app.agents.tool_registry import TOOL_SCHEMAS, TOOLS_BY_NAME, ToolOutcome, execute_tool
from app.memory import conversation_store as mem
from app.utils.logger import log_interaction, logger

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_ITERATIONS = 5
REQUEST_TIMEOUT_S = float(os.getenv("GROQ_TIMEOUT_S", "30"))
MAX_ATTEMPTS = int(os.getenv("GROQ_MAX_ATTEMPTS", "3"))
BACKOFF_BASE_S = 1.0

# Transient failures worth retrying. Auth and bad-request errors are not.
_RETRYABLE = (
    groq.APIConnectionError,  # also the base class of APITimeoutError
    groq.RateLimitError,
    groq.InternalServerError,
)


class AgentConfigError(RuntimeError):
    """The agent cannot run because it is not configured (no API key)."""


class LLMUnavailableError(RuntimeError):
    """The LLM provider failed after all retries."""


@dataclass
class AgentResult:
    response: str
    status: str  # "ok" or "error"
    intent: str
    tools_used: List[str]
    tool_calls: List[Dict[str, Any]]
    # Messages produced this turn in OpenAI chat format, ready to be persisted.
    new_messages: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    error_detail: Optional[str] = None


_client: Optional[Groq] = None


def get_client() -> Groq:
    """Create the Groq client on first use. SDK retries are off; we retry explicitly."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise AgentConfigError("GROQ_API_KEY is not set")
        _client = Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_S, max_retries=0)
    return _client


def _build_system_prompt(student_id: str, student_name: str, student_class: str) -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    return f"""You are an intelligent AI School ERP Assistant for Delhi Public School.
You help students, teachers, and parents with school-related queries using natural language.

Current Student: {student_name} (ID: {student_id}), Class {student_class}
Today: {today}

Guidelines:
- Always use the available ERP tools to fetch real data before responding. Never guess data.
- For multi-part queries (e.g., "show attendance and marks"), call ALL relevant tools.
- If a tool returns an error, read it and retry with corrected arguments or explain the problem.
- Respond in a friendly, encouraging, and professional tone.
- Format responses clearly with numbers, bullet points, and emojis where helpful.
- When data shows concerns (low attendance, low marks, pending fees), gently flag them.
- Always include actionable advice when relevant.
- Keep responses concise but informative.
"""


def _detect_intent(tools_used: List[str]) -> str:
    if not tools_used:
        return "General Query"
    names = []
    for t in tools_used:
        label = TOOLS_BY_NAME[t].intent if t in TOOLS_BY_NAME else t
        if label not in names:
            names.append(label)
    return " + ".join(names)


def _create_completion(client: Any, messages: List[Dict[str, Any]]) -> Any:
    """Call the chat API with a timeout, retrying transient errors with backoff."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=2048,
                temperature=0.3,
                timeout=REQUEST_TIMEOUT_S,
            )
        except _RETRYABLE as exc:
            if attempt == MAX_ATTEMPTS:
                logger.error(f"Groq request failed after {attempt} attempts: {exc}")
                raise LLMUnavailableError(f"LLM request failed after {attempt} attempts: {exc}") from exc
            delay = BACKOFF_BASE_S * 2 ** (attempt - 1) + random.uniform(0, 0.25)
            logger.warning(f"Groq attempt {attempt} failed ({type(exc).__name__}); retrying in {delay:.2f}s")
            time.sleep(delay)
        except groq.APIError as exc:
            logger.error(f"Groq request rejected: {exc}")
            raise LLMUnavailableError(f"LLM request rejected: {exc}") from exc


def _tool_call_record(outcome: ToolOutcome) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "name": outcome.name,
        "arguments": outcome.arguments,
        "status": outcome.status,
    }
    if outcome.error:
        record["error"] = outcome.error
    return record


def run_agent(
    message: str,
    student_id: str,
    session_id: str,
    student_name: str = "Student",
    student_class: str = "10-A",
    client: Any = None,
) -> AgentResult:
    """Run one user turn: call the model, execute requested tools, loop until it answers."""
    start = time.time()
    client = client or get_client()
    system_prompt = _build_system_prompt(student_id, student_name, student_class)
    history = mem.get_conversation_messages(session_id)

    user_message = {"role": "user", "content": message}
    new_messages: List[Dict[str, Any]] = [user_message]
    messages = [{"role": "system", "content": system_prompt}, *history, user_message]

    outcomes: List[ToolOutcome] = []
    final_response: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None

    for _ in range(MAX_ITERATIONS):
        completion = _create_completion(client, messages)
        msg = completion.choices[0].message

        if not msg.tool_calls:
            if msg.content:
                final_response = msg.content
            else:
                error, error_detail = "empty_model_response", "The model returned no text and no tool calls."
            break

        assistant_msg = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)
        new_messages.append(assistant_msg)

        for tc in msg.tool_calls:
            outcome = execute_tool(tc.function.name, tc.function.arguments, student_id)
            logger.info(
                f"Tool {outcome.name} status={outcome.status} args={outcome.arguments} student={student_id}"
            )
            outcomes.append(outcome)
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(outcome.result, default=str),
            }
            messages.append(tool_msg)
            new_messages.append(tool_msg)
    else:
        error = "max_iterations_exceeded"
        error_detail = f"The model was still requesting tools after {MAX_ITERATIONS} rounds."

    tools_used = [o.name for o in outcomes if o.executed]
    intent = _detect_intent(tools_used)
    tool_calls = [_tool_call_record(o) for o in outcomes]

    if final_response is not None:
        new_messages.append({"role": "assistant", "content": final_response})
    log_interaction(message, intent, tools_used, time.time() - start, final_response or "", student_id)

    return AgentResult(
        response=final_response or "",
        status="error" if error else "ok",
        intent=intent,
        tools_used=tools_used,
        tool_calls=tool_calls,
        new_messages=new_messages,
        error=error,
        error_detail=error_detail,
    )
