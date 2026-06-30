# AI School ERP Assistant

An AI-powered School ERP Assistant built with **FastAPI** and **Groq (llama-3.3-70b-versatile)**. Understands natural language queries, autonomously selects the right ERP tools, maintains conversation context, and returns structured responses.

---

## Architecture

```
User Query
    │
    ▼
POST /chat  (FastAPI)
    │
    ▼
ERP Agent (Groq llama-3.3-70b-versatile)
    │  ┌── Intent Detection
    │  ├── Tool Selection (function calling)
    │  └── Agentic Loop (up to 5 iterations)
    │
    ├── get_attendance     → mock_data/attendance.json
    ├── get_marks          → mock_data/marks.json
    ├── get_fees           → mock_data/fees.json
    ├── get_homework       → mock_data/homework.json
    ├── get_timetable      → mock_data/timetable.json
    ├── get_academic_summary   (aggregates all)
    ├── get_recommendations    (AI analysis)
    ├── get_attendance_insights (projection)
    └── get_parent_report      (comprehensive)
         │
         ▼
    Conversation Memory (SQLite)
         │
         ▼
    Structured JSON Response
```

## Features

| Feature | Details |
|---|---|
| Natural Language Understanding | Groq LLM with function calling |
| Agent Planning | Logged execution plan in every response |
| Multi-Step Execution | Parallel tool calls in one query |
| Conversation Memory | SQLite-backed session history |
| ERP Tools | 9 tools across 5 domains + 4 analytics |
| Bonus: Academic Summary | Overall grade, strong/weak subjects |
| Bonus: Smart Recommendations | AI-driven study suggestions |
| Bonus: Attendance Insights | Projection to target % |
| Bonus: Parent Report | Full progress report |

## Setup

### 1. Clone & install

```bash
cd /path/to/school-erp
pip install -r requirements.txt
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

Open http://localhost:8000/docs for interactive Swagger UI.

---

## API Reference

### POST /chat

```json
{
  "message": "Show my attendance for this month.",
  "student_id": "S001",
  "session_id": "optional-uuid-for-continuity"
}
```

**Response:**
```json
{
  "intent": "Attendance",
  "response": "Your attendance for June 2026 is 86.36%...",
  "status": "Fetched",
  "tools_used": ["get_attendance"],
  "execution_plan": "Step 1: Intent Detection → \"Attendance\"\nStep 2: ...",
  "session_id": "uuid",
  "execution_time_ms": 1240.5
}
```

### GET /chat/history

```
GET /chat/history?session_id=<uuid>
GET /chat/history?student_id=S001
```

### GET /chat/sessions

```
GET /chat/sessions?student_id=S001
```

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
| `mock_data/students.json` | Student profiles (S001, S002, S003) |
| `mock_data/attendance.json` | Daily attendance for May–June 2026 |
| `mock_data/marks.json` | Mid-term scores for 6 subjects |
| `mock_data/fees.json` | Annual fee structure and payment history |
| `mock_data/homework.json` | Pending and completed assignments |
| `mock_data/timetable.json` | Mon–Fri class schedule for 10-A |

Default student: **Arjun Sharma (S001)**, Class **10-A**

---

## Project Structure

```
school-erp/
├── app/
│   ├── api/chat.py          # FastAPI routes
│   ├── agents/erp_agent.py  # Groq agent + agentic loop
│   ├── tools/               # 9 ERP tool functions
│   ├── memory/              # SQLite conversation store
│   ├── models/schemas.py    # Pydantic models
│   ├── utils/logger.py      # Loguru structured logging
│   └── main.py              # FastAPI app entry point
├── mock_data/               # JSON mock ERP data
├── logs/                    # Auto-generated log files
├── requirements.txt
└── .env.example
```

## Logging

All interactions are logged to `logs/erp_assistant.log`:
```
2026-06-30 10:15:42 | INFO | INTERACTION | {
  "student_id": "S001",
  "user_query": "Show my marks",
  "identified_intent": "Marks & Grades",
  "selected_tools": ["get_marks"],
  "execution_time_ms": 1240.5,
  "response_preview": "Here are your marks..."
}
```
