import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

from app.tools.attendance_tool import get_attendance
from app.tools.marks_tool import get_marks
from app.tools.fees_tool import get_fees
from app.tools.homework_tool import get_homework
from app.tools.timetable_tool import get_timetable
from app.tools.analytics_tool import (
    get_academic_summary,
    get_recommendations,
    get_attendance_insights,
    get_parent_report,
)
from app.memory import conversation_store as mem
from app.utils.logger import log_interaction, logger

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_attendance",
            "description": "Get attendance records for the student. Use for queries about attendance, absences, classes missed, attendance percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "Month in YYYY-MM format. Defaults to current month."},
                    "period": {
                        "type": "string",
                        "enum": ["today", "week", "month", "semester"],
                        "description": "Time period. Default: month",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_marks",
            "description": "Get marks/scores for subjects. Use for queries about grades, scores, performance, subject marks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Subject name (e.g. Mathematics, Physics). Leave empty for all subjects.",
                    },
                    "exam_type": {
                        "type": "string",
                        "enum": ["mid_term", "unit_test", "assignment", "all"],
                        "description": "Type of exam. Default: all",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fees",
            "description": "Get fee payment status, payment history, and pending dues. Use for queries about fees, payments, dues.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_homework",
            "description": "Get homework and assignment details. Use for queries about homework, assignments, tasks due.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_by": {
                        "type": "string",
                        "enum": ["pending", "today", "tomorrow", "completed", "overdue", "all"],
                        "description": "Filter homework by status. Default: pending",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject name. Optional.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timetable",
            "description": "Get class schedule/timetable. Use for queries about schedule, classes, what subject is next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day of week (Monday-Friday). Leave empty for today/tomorrow overview.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Find when a specific subject is scheduled.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_academic_summary",
            "description": "Get comprehensive academic performance summary. Use for overall performance, semester summary, progress reports.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "Get personalized study recommendations and improvement suggestions based on performance data.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_insights",
            "description": "Calculate attendance projections and insights. Use for questions like 'Can I maintain 90% attendance?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_percentage": {
                        "type": "number",
                        "description": "Target attendance percentage. Default: 90.0",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_parent_report",
            "description": "Generate a comprehensive parent progress report covering attendance, marks, homework, fees, and AI suggestions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_FUNCTIONS = {
    "get_attendance": get_attendance,
    "get_marks": get_marks,
    "get_fees": get_fees,
    "get_homework": get_homework,
    "get_timetable": get_timetable,
    "get_academic_summary": get_academic_summary,
    "get_recommendations": get_recommendations,
    "get_attendance_insights": get_attendance_insights,
    "get_parent_report": get_parent_report,
}

INTENT_MAP = {
    "get_attendance": "Attendance",
    "get_marks": "Marks & Grades",
    "get_fees": "Fee Status",
    "get_homework": "Homework",
    "get_timetable": "Timetable",
    "get_academic_summary": "Academic Summary",
    "get_recommendations": "Recommendations",
    "get_attendance_insights": "Attendance Insights",
    "get_parent_report": "Parent Report",
}


def _build_system_prompt(student_id: str, student_name: str, student_class: str) -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    return f"""You are an intelligent AI School ERP Assistant for Delhi Public School.
You help students, teachers, and parents with school-related queries using natural language.

Current Student: {student_name} (ID: {student_id}), Class {student_class}
Today: {today}

Guidelines:
- Always use the available ERP tools to fetch real data before responding. Never guess data.
- For multi-part queries (e.g., "show attendance and marks"), call ALL relevant tools.
- Respond in a friendly, encouraging, and professional tone.
- Format responses clearly with numbers, bullet points, and emojis where helpful.
- When data shows concerns (low attendance, low marks, pending fees), gently flag them.
- Always include actionable advice when relevant.
- Keep responses concise but informative.
"""


def _execute_tool(name: str, args: dict, student_id: str) -> Any:
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return {"error": f"Unknown tool: {name}"}
    if name in ("get_attendance", "get_marks", "get_fees", "get_homework",
                "get_timetable", "get_academic_summary", "get_recommendations",
                "get_attendance_insights", "get_parent_report"):
        return func(student_id=student_id, **args)
    return func(**args)


def _detect_intent(tools_used: List[str]) -> str:
    if not tools_used:
        return "General Query"
    if len(tools_used) > 1:
        intents = [INTENT_MAP.get(t, t) for t in tools_used]
        return " + ".join(intents)
    return INTENT_MAP.get(tools_used[0], "General Query")


def _build_execution_plan(query: str, intent: str, tools_used: List[str]) -> str:
    tools_str = ", ".join(tools_used) if tools_used else "No ERP tool needed"
    return (
        f"Step 1: Intent Detection → {intent}\n"
        f"Step 2: Tool Selection → {tools_str}\n"
        "Step 3: Data Retrieval → Fetched live ERP data\n"
        "Step 4: Response Generation → Formatted natural language response"
    )


def run_agent(
    message: str,
    student_id: str,
    session_id: str,
    student_name: str = "Student",
    student_class: str = "10-A",
) -> Tuple[str, List[str], str]:
    start = time.time()
    system_prompt = _build_system_prompt(student_id, student_name, student_class)
    history = mem.get_openai_messages(session_id, limit=10)

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": message},
    ]

    tools_used: List[str] = []
    final_response = "I encountered an issue processing your request. Please try again."

    for iteration in range(5):
        try:
            completion = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=2048,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise

        msg = completion.choices[0].message

        if not msg.tool_calls:
            final_response = msg.content or final_response
            break

        messages.append({
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
        })

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) or {}
            except (json.JSONDecodeError, TypeError):
                args = {}

            logger.info(f"Calling tool: {tool_name} args={args} student={student_id}")
            result = _execute_tool(tool_name, args, student_id)
            tools_used.append(tool_name)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    intent = _detect_intent(tools_used)
    exec_time = time.time() - start
    log_interaction(message, intent, tools_used, exec_time, final_response, student_id)

    return final_response, tools_used, intent
