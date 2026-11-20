"""Tool definitions: one Pydantic argument model per tool.

The JSON schema sent to the LLM is generated from the same models that
validate the LLM's arguments, so the two cannot drift apart.
"""
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.analytics_tool import (
    get_academic_summary,
    get_attendance_insights,
    get_parent_report,
    get_recommendations,
)
from app.tools.attendance_tool import get_attendance
from app.tools.exam_planner_tool import get_exam_plan
from app.tools.fees_tool import get_fees
from app.tools.homework_tool import get_homework
from app.tools.marks_tool import get_marks
from app.tools.timetable_tool import get_timetable


class ToolArgs(BaseModel):
    """Base for tool arguments. Unknown arguments are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


class AttendanceArgs(ToolArgs):
    month: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format. Defaults to the current month.",
    )
    period: Literal["today", "week", "month", "semester"] = Field(
        "month", description="Time period."
    )


class MarksArgs(ToolArgs):
    subject: Optional[str] = Field(
        None,
        description="Subject name (e.g. Mathematics, Physics). Omit for all subjects.",
    )
    exam_type: Optional[Literal["mid_term", "unit_test", "assignment", "all"]] = Field(
        None,
        description="Accepted for compatibility; the result always contains all exam types.",
    )


class HomeworkArgs(ToolArgs):
    filter_by: Literal["pending", "today", "tomorrow", "completed", "overdue", "all"] = Field(
        "pending", description="Filter homework by status."
    )
    subject: Optional[str] = Field(None, description="Filter by subject name.")


class TimetableArgs(ToolArgs):
    day: Optional[str] = Field(
        None,
        description="Day of week (Monday-Friday). Omit for a today/tomorrow overview.",
    )
    subject: Optional[str] = Field(
        None, description="Find when a specific subject is scheduled."
    )


class AttendanceInsightsArgs(ToolArgs):
    target_percentage: float = Field(
        90.0, ge=0, le=100, description="Target attendance percentage."
    )


class ExamPlanArgs(ToolArgs):
    days_until_exam: int = Field(
        15, ge=1, le=90, description="Number of days until the exam starts."
    )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: Type[ToolArgs]
    func: Callable[..., Any]
    intent: str


TOOLS: List[Tool] = [
    Tool(
        "get_attendance",
        "Get attendance records for the student. Use for queries about attendance, "
        "absences, classes missed, attendance percentage.",
        AttendanceArgs, get_attendance, "Attendance",
    ),
    Tool(
        "get_marks",
        "Get marks/scores for subjects. Use for queries about grades, scores, "
        "performance, subject marks.",
        MarksArgs, get_marks, "Marks & Grades",
    ),
    Tool(
        "get_fees",
        "Get fee payment status, payment history, and pending dues. Use for queries "
        "about fees, payments, dues.",
        NoArgs, get_fees, "Fee Status",
    ),
    Tool(
        "get_homework",
        "Get homework and assignment details. Use for queries about homework, "
        "assignments, tasks due.",
        HomeworkArgs, get_homework, "Homework",
    ),
    Tool(
        "get_timetable",
        "Get class schedule/timetable. Use for queries about schedule, classes, "
        "what subject is next.",
        TimetableArgs, get_timetable, "Timetable",
    ),
    Tool(
        "get_academic_summary",
        "Get comprehensive academic performance summary. Use for overall performance, "
        "semester summary, progress reports.",
        NoArgs, get_academic_summary, "Academic Summary",
    ),
    Tool(
        "get_recommendations",
        "Get study recommendations and improvement suggestions. Generated from "
        "fixed rules over the student's marks and attendance.",
        NoArgs, get_recommendations, "Recommendations",
    ),
    Tool(
        "get_attendance_insights",
        "Calculate attendance projections and insights. Use for questions like "
        "'Can I maintain 90% attendance?'",
        AttendanceInsightsArgs, get_attendance_insights, "Attendance Insights",
    ),
    Tool(
        "get_parent_report",
        "Generate a comprehensive parent progress report covering attendance, marks, "
        "homework, fees, and rule-based suggestions.",
        NoArgs, get_parent_report, "Parent Report",
    ),
    Tool(
        "get_exam_plan",
        "Generate a day-by-day exam study plan weighted towards weaker subjects. Use "
        "for queries like 'My exams start in X days, create a study plan' or 'Help me "
        "prepare for exams'.",
        ExamPlanArgs, get_exam_plan, "Exam Planner",
    ),
]

TOOLS_BY_NAME: Dict[str, Tool] = {t.name: t for t in TOOLS}


def _clean_schema(node: Any) -> Any:
    """Make a pydantic JSON schema simpler for LLM tool-calling APIs."""
    if isinstance(node, dict):
        node = {k: _clean_schema(v) for k, v in node.items()
                if k != "title" and not (k == "default" and v is None)}
        # Optional[X] is emitted as anyOf [X, null]; the API only needs X.
        options = node.get("anyOf")
        if options:
            non_null = [o for o in options if o.get("type") != "null"]
            if len(non_null) == 1:
                node = {**{k: v for k, v in node.items() if k != "anyOf"}, **non_null[0]}
        return node
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def build_tool_schemas() -> List[Dict[str, Any]]:
    schemas = []
    for t in TOOLS:
        params = _clean_schema(t.args_model.model_json_schema())
        params.pop("additionalProperties", None)
        params.setdefault("properties", {})
        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": params,
            },
        })
    return schemas


TOOL_SCHEMAS = build_tool_schemas()


@dataclass
class ToolOutcome:
    """Result of one tool call, as sent back to the model and reported to the API."""

    name: str
    arguments: Dict[str, Any]
    status: str  # ok | tool_error | invalid_arguments | unknown_tool
    result: Any

    @property
    def executed(self) -> bool:
        return self.status in ("ok", "tool_error")

    @property
    def error(self) -> Optional[str]:
        if self.status == "ok":
            return None
        return self.result.get("error") if isinstance(self.result, dict) else str(self.result)


def parse_arguments(raw: Any) -> Dict[str, Any]:
    """Decode the model's argument string into a dict; raises ValueError if unusable."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"arguments are not valid JSON: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("arguments must be a JSON object")
    return parsed


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "arguments"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def execute_tool(name: str, raw_arguments: Any, student_id: str) -> ToolOutcome:
    """Validate arguments, run the tool, and never raise.

    Problems are returned as an {"error": ...} result so the model can read
    them and retry with corrected arguments.
    """
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return ToolOutcome(
            name, {}, "unknown_tool",
            {"error": f"Unknown tool '{name}'. Available tools: {sorted(TOOLS_BY_NAME)}"},
        )

    try:
        args = parse_arguments(raw_arguments)
    except ValueError as exc:
        return ToolOutcome(name, {}, "invalid_arguments", {"error": f"Invalid arguments for {name}: {exc}"})

    # Models often send null for "not specified"; treat that as omitted.
    args = {k: v for k, v in args.items() if v is not None}

    try:
        validated = tool.args_model(**args)
    except ValidationError as exc:
        return ToolOutcome(
            name, args, "invalid_arguments",
            {"error": f"Invalid arguments for {name}: {_format_validation_error(exc)}"},
        )

    clean_args = validated.model_dump(exclude_none=True)
    try:
        result = tool.func(student_id=student_id, **clean_args)
    except Exception as exc:  # tool bugs or bad data files must not crash the turn
        return ToolOutcome(name, clean_args, "tool_error", {"error": f"{name} failed: {exc}"})

    status = "tool_error" if isinstance(result, dict) and "error" in result else "ok"
    return ToolOutcome(name, clean_args, status, result)
