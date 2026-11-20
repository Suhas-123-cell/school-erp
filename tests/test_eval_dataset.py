import importlib.util
import json
from pathlib import Path

from app.agents.erp_agent import AgentResult
from app.agents.tool_registry import TOOLS_BY_NAME

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_eval", EVAL_DIR / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dataset_is_well_formed():
    runner = _load_runner()
    cases = runner.load_cases()
    assert len(cases) >= 20
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["query"].strip()
        assert set(case["expected_tools"]) <= set(TOOLS_BY_NAME)
        for tool, args in case.get("expected_args", {}).items():
            assert tool in case["expected_tools"]
            TOOLS_BY_NAME[tool].args_model(**args)  # expected args must themselves be valid


def _result(calls):
    return AgentResult("", "ok", "x", [], calls)


def test_scoring_exact_match_and_args():
    runner = _load_runner()
    case = {"id": "t", "query": "q", "expected_tools": ["get_marks"],
            "expected_args": {"get_marks": {"subject": "Physics"}}}

    good = runner.score_case(case, _result([
        {"name": "get_marks", "arguments": {"subject": "Physics"}, "status": "ok"}]))
    assert good["tool_selection_exact"] and good["args_ok"] is True

    wrong_arg = runner.score_case(case, _result([
        {"name": "get_marks", "arguments": {"subject": "Maths"}, "status": "ok"}]))
    assert wrong_arg["tool_selection_exact"] and wrong_arg["args_ok"] is False

    extra_tool = runner.score_case(case, _result([
        {"name": "get_marks", "arguments": {"subject": "Physics"}, "status": "ok"},
        {"name": "get_fees", "arguments": {}, "status": "ok"}]))
    assert not extra_tool["tool_selection_exact"]


def test_scoring_no_tool_expected_and_invalid_calls():
    runner = _load_runner()
    none_case = {"id": "n", "query": "hi", "expected_tools": []}
    assert runner.score_case(none_case, _result([]))["tool_selection_exact"]

    case = {"id": "t", "query": "q", "expected_tools": ["get_fees"]}
    row = runner.score_case(case, _result([
        {"name": "get_fees", "arguments": {"x": 1}, "status": "invalid_arguments", "error": "e"},
        {"name": "get_fees", "arguments": {}, "status": "ok"}]))
    assert row["invalid_calls"] == 1 and row["tool_selection_exact"]
