import json

import pytest

from app.agents.tool_registry import TOOL_SCHEMAS, TOOLS, execute_tool


def test_every_tool_has_a_schema_generated_from_its_model():
    assert [s["function"]["name"] for s in TOOL_SCHEMAS] == [t.name for t in TOOLS]
    for s in TOOL_SCHEMAS:
        params = s["function"]["parameters"]
        assert params["type"] == "object"
        assert "title" not in params
        assert "anyOf" not in json.dumps(params)


def test_valid_call_runs_the_tool():
    out = execute_tool("get_marks", {"subject": "Mathematics"}, "S001")
    assert out.status == "ok"
    assert out.arguments == {"subject": "Mathematics"}
    assert out.result["subject"] == "Mathematics"


def test_json_string_arguments_are_parsed_and_defaults_filled():
    out = execute_tool("get_homework", '{"subject": "Physics"}', "S001")
    assert out.status == "ok"
    assert out.arguments == {"filter_by": "pending", "subject": "Physics"}


def test_numbers_sent_as_strings_are_coerced():
    out = execute_tool("get_exam_plan", {"days_until_exam": "7"}, "S001")
    assert out.status == "ok"
    assert out.arguments == {"days_until_exam": 7}
    assert len(out.result["daily_plan"]) == 7


def test_null_arguments_are_treated_as_omitted():
    out = execute_tool("get_attendance", {"month": None, "period": None}, "S001")
    assert out.status == "ok"
    assert out.arguments == {"period": "month"}


def test_empty_arguments_for_no_arg_tool():
    for raw in ("", "{}", None, "null"):
        assert execute_tool("get_fees", raw, "S001").status == "ok"


def test_hallucinated_argument_is_rejected_not_passed_through():
    out = execute_tool("get_fees", {"student_name": "Arjun"}, "S001")
    assert out.status == "invalid_arguments"
    assert not out.executed
    assert "student_name" in out.result["error"]


def test_model_cannot_override_student_id():
    out = execute_tool("get_marks", {"student_id": "S002"}, "S001")
    assert out.status == "invalid_arguments"


@pytest.mark.parametrize("name,args", [
    ("get_attendance", {"period": "year"}),
    ("get_attendance", {"month": "June 2026"}),
    ("get_homework", {"filter_by": "soon"}),
    ("get_attendance_insights", {"target_percentage": 150}),
    ("get_attendance_insights", {"target_percentage": "high"}),
    ("get_exam_plan", {"days_until_exam": 0}),
    ("get_exam_plan", {"days_until_exam": 100000}),
])
def test_out_of_range_values_return_validation_errors(name, args):
    out = execute_tool(name, args, "S001")
    assert out.status == "invalid_arguments"
    assert out.result["error"].startswith(f"Invalid arguments for {name}")


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]", '"text"'])
def test_malformed_argument_payloads(raw):
    out = execute_tool("get_marks", raw, "S001")
    assert out.status == "invalid_arguments"


def test_unknown_tool_lists_available_tools():
    out = execute_tool("delete_student", {}, "S001")
    assert out.status == "unknown_tool"
    assert "get_marks" in out.result["error"]


def test_tool_level_error_is_flagged():
    out = execute_tool("get_marks", {"subject": "Astrology"}, "S001")
    assert out.status == "tool_error"
    assert out.executed
    assert "not found" in out.error


def test_exception_inside_a_tool_becomes_an_error_result(monkeypatch):
    from app.agents import tool_registry

    def boom(student_id):
        raise FileNotFoundError("fees.json")

    tool = tool_registry.TOOLS_BY_NAME["get_fees"]
    monkeypatch.setitem(tool_registry.TOOLS_BY_NAME, "get_fees", type(tool)(
        tool.name, tool.description, tool.args_model, boom, tool.intent))
    out = execute_tool("get_fees", {}, "S001")
    assert out.status == "tool_error"
    assert "fees.json" in out.error
