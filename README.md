# AI School ERP Assistant

An AI-powered School ERP Assistant built with **FastAPI** and **Groq (llama-3.3-70b-versatile)**. Understands natural language queries, lets the model choose among ERP tools via function calling, keeps conversation context, and returns structured responses.

---

## Architecture

```
POST /chat (FastAPI, async)
    │  run_in_threadpool  (the agent is synchronous; it stays off the event loop)
    ▼
run_agent  (app/agents/erp_agent.py)
    │  1. load stored history for the session, trimmed to a token budget
    │  2. call Groq with the tool schemas (timeout + bounded retries with backoff)
    │  3. for each tool call the model requests:
    │        validate the arguments with that tool's Pydantic model
    │        valid   -> run the tool (student_id always comes from the request, never the model)
    │        invalid -> the validation error is returned to the model as the tool result
    │  4. repeat up to 5 rounds until the model answers in text
    ▼
mock JSON data (mock_data/*.json) via app/tools/*
    ▼
SQLite conversation store (user, assistant tool calls, tool results, final answers)
```

Tools (`app/agents/tool_registry.py`): `get_attendance`, `get_marks`, `get_fees`,
`get_homework`, `get_timetable`, `get_academic_summary`, `get_recommendations`,
`get_attendance_insights`, `get_parent_report`, `get_exam_plan`. Each has a Pydantic
argument model; the JSON schema sent to the model is generated from the same model.

## How it works

| Area | Behaviour |
|---|---|
| Tool selection | The LLM picks tools through Groq function calling. There is no separate planner. |
| Argument validation | Unknown arguments, bad enums, out-of-range numbers and malformed JSON are rejected before any tool runs. The error text goes back to the model as the tool result so it can retry. Unknown tool names are handled the same way. `null` arguments are treated as omitted. |
| Execution trace | Every response lists the tool calls that were actually made (`tool_calls`: name, validated arguments, status). It is a record of what happened, not a plan made in advance. |
| Memory | SQLite. Assistant tool calls and tool results are stored with the conversation, so a later turn can see data fetched earlier. They are hidden from `/chat/history` and `/chat/sessions`. |
| History trimming | Replayed history is limited by an approximate token budget (`HISTORY_TOKEN_BUDGET`, default 4000, estimated as characters / 4). Whole turns are dropped oldest first, so a tool call is never separated from its result. |
| LLM failures | 30 s timeout per request (`GROQ_TIMEOUT_S`), up to 3 attempts (`GROQ_MAX_ATTEMPTS`) with exponential backoff on connection errors, timeouts, rate limits and 5xx. Still failing -> HTTP 502. Missing API key -> HTTP 503. |
| Loop limit | If the model is still asking for tools after 5 rounds, the response has `status: "error"` and `error: "max_iterations_exceeded"`. The turn is not stored. |
| Recommendations, study plan, parent report | Rule-based Python (thresholds on marks and attendance). They are not model-generated. The LLM only phrases the final answer. |
| Attendance insights | Assumes 45 remaining classes (a constant in `analytics_tool.py`), not taken from a calendar. |

Limitations: single-tenant mock data with no authentication, tools run sequentially,
the token estimate is a heuristic rather than a tokenizer, and `get_marks` accepts
`exam_type` but always returns all exam types.

## Setup

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # adds pytest and httpx for the tests
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

Get a free Groq API key at: https://console.groq.com

### 3. Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive Swagger UI. The app can be started
from any directory; data, frontend and log paths are resolved from the source tree.

### Docker

```bash
docker build -t school-erp .
docker run --rm -p 8000:8000 -e GROQ_API_KEY=... school-erp
```

Without `GROQ_API_KEY` the container starts and `/health` works, but `POST /chat`
returns 503. Conversation history is stored inside the container
(`/srv/school-erp/logs/conversations.db`); mount a volume there to keep it.

### Tests

```bash
pytest
```

The tests use a fake Groq client, so they need no API key or network. They cover tool
dispatch, argument validation, retries, memory persistence and trimming, and the HTTP
endpoints.

### Tool-selection eval

`eval/tool_selection.jsonl` holds labelled queries (query -> expected tool names, and
for some, expected argument values). `eval/run_eval.py` runs them against the live
model and writes raw per-query results to `eval/results/`:

```bash
GROQ_API_KEY=... python eval/run_eval.py --delay 2
```

It needs a real API key and makes real requests. No results are included in this
repository.

---

## API Reference

### POST /chat

```json
{
  "message": "Show my Mathematics marks.",
  "student_id": "S001",
  "session_id": "optional-uuid-for-continuity"
}
```

**Response (shape; values are illustrative):**
```json
{
  "intent": "Marks & Grades",
  "response": "...",
  "status": "Fetched",
  "tools_used": ["get_marks"],
  "tool_calls": [
    {"name": "get_marks", "arguments": {"subject": "Mathematics"}, "status": "ok", "error": null}
  ],
  "error": null,
  "error_detail": null,
  "session_id": "uuid",
  "execution_time_ms": 1240.5
}
```

`tool_calls[].status` is one of `ok`, `tool_error` (the tool ran but reported an error),
`invalid_arguments` or `unknown_tool` (rejected; the model was told why). `tools_used`
lists only the calls that actually ran.

`status` is `Fetched`, `Generated`, `Calculated` or `Answered` on success and `error`
when the agent did not produce an answer (`error` holds the code, for example
`max_iterations_exceeded` or `empty_model_response`). Other failures use HTTP status
codes: 404 unknown student, 502 LLM provider unavailable after retries, 503 no API key.

### GET /chat/history

```
GET /chat/history?session_id=<uuid>
GET /chat/history?student_id=S001
```

### GET /chat/sessions

```
GET /chat/sessions?student_id=S001
```

### /students

`GET /students`, `POST /students`, `DELETE /students/{id}` edit `mock_data/students.json` directly.

---

## Example Queries

```
# Attendance
"Show my attendance for this month."
"How many classes did I miss?"
"Can I maintain 90% attendance this semester?"

# Marks
"Show my Mathematics marks."
"Which subject has the highest marks?"
"What is my average score?"

# Fees
"Have I paid this month's fees?"
"How much fee is pending?"
"Show payment history."

# Homework
"What homework is pending?"
"Show today's homework."
"What assignments are due tomorrow?"

# Timetable
"Show tomorrow's timetable."
"What is my first class today?"
"When is my Mathematics class?"

# Multi-step (bonus)
"Show my attendance, marks, and tell me if I have pending fees."
"Summarize my academic performance this semester."
"How can I improve my grades?"
"Generate a parent progress report."
```

---

## Mock Data

| File | Contents |
|---|---|
| `mock_data/students.json` | Student profiles (S001 to S004) |
| `mock_data/attendance.json` | Daily attendance for May and June 2026 (S001, S002) |
| `mock_data/marks.json` | Mid-term, unit test and assignment scores for 6 subjects (S001, S002) |
| `mock_data/fees.json` | Annual fee structure and payment history (S001, S002) |
| `mock_data/homework.json` | Pending and completed assignments per class (10-A, 10-B) |
| `mock_data/timetable.json` | Mon-Fri class schedule for 10-A |

Default student: **Arjun Sharma (S001)**, Class **10-A**. Students without records in a
file (for example S003 for marks) get a tool error, which the model relays.

---

## Project Structure

```
school-erp/
├── app/
│   ├── api/                 # chat and students routes
│   ├── agents/
│   │   ├── erp_agent.py     # Groq client, retries, agent loop
│   │   └── tool_registry.py # Pydantic argument models, schemas, validated dispatch
│   ├── tools/               # ERP tool functions over the mock data
│   ├── services/            # thin wrappers around the tools
│   ├── memory/              # SQLite conversation store
│   ├── models/schemas.py    # API response models
│   ├── paths.py             # data, frontend and log locations
│   ├── utils/logger.py      # Loguru logging
│   └── main.py              # FastAPI app entry point
├── frontend/                # static chat UI
├── mock_data/               # JSON mock ERP data
├── tests/                   # pytest suite (mocked Groq client)
├── eval/                    # tool-selection dataset and runner
├── Dockerfile
└── requirements.txt
```

## Logging

Each interaction is logged to `logs/erp_assistant.log` as one line:
```
2026-06-30 10:15:42 | INFO | INTERACTION | {"timestamp": "...", "student_id": "S001", "user_query": "Show my marks", "identified_intent": "Marks & Grades", "selected_tools": ["get_marks"], "execution_time_ms": 1240.5, "response_preview": "..."}
```
