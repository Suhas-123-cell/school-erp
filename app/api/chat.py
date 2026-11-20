import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.agents.erp_agent import AgentConfigError, LLMUnavailableError, run_agent
from app.memory import conversation_store as mem
from app.models.schemas import ChatHistoryResponse, ChatRequest, ChatResponse, HistoryMessage
from app.paths import MOCK_DATA_DIR
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["Chat"])

_STATUS_BY_INTENT = {
    "Attendance": "Fetched",
    "Marks & Grades": "Fetched",
    "Fee Status": "Fetched",
    "Homework": "Fetched",
    "Timetable": "Fetched",
    "Academic Summary": "Generated",
    "Recommendations": "Generated",
    "Attendance Insights": "Calculated",
    "Parent Report": "Generated",
    "Exam Planner": "Generated",
    "General Query": "Answered",
}


def _get_student_info(student_id: str) -> Optional[dict]:
    """Return the student's record, or None if the ID is unknown."""
    with open(MOCK_DATA_DIR / "students.json") as f:
        return json.load(f).get(student_id)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    student_id = request.student_id or "S001"
    student_info = _get_student_info(student_id)
    if student_info is None:
        raise HTTPException(status_code=404, detail=f"Student ID {student_id} not found")

    session_id = request.session_id or mem.generate_session_id()
    start = time.time()

    # run_agent is synchronous (blocking HTTP + SQLite), so keep it off the event loop.
    try:
        result = await run_in_threadpool(
            run_agent,
            message=request.message,
            student_id=student_id,
            session_id=session_id,
            student_name=student_info.get("name", "Student"),
            student_class=student_info.get("class", "10-A"),
        )
    except AgentConfigError as e:
        logger.error(f"Agent not configured: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except LLMUnavailableError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if result.status == "ok":
        await run_in_threadpool(
            mem.save_turn, session_id, student_id, result.new_messages,
            result.intent, result.tools_used,
        )
        base_intent = result.intent.split(" + ")[0]
        status = _STATUS_BY_INTENT.get(base_intent, "Completed")
    else:
        # A failed turn is not stored, so the next turn does not replay it.
        status = "error"

    return ChatResponse(
        intent=result.intent,
        response=result.response,
        status=status,
        tools_used=result.tools_used,
        tool_calls=result.tool_calls,
        error=result.error,
        error_detail=result.error_detail,
        session_id=session_id,
        execution_time_ms=round((time.time() - start) * 1000, 2),
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_history(
    session_id: Optional[str] = Query(None, description="Session ID"),
    student_id: Optional[str] = Query(None, description="Student ID"),
):
    if not session_id and not student_id:
        raise HTTPException(status_code=400, detail="Provide session_id or student_id")

    if session_id:
        raw = mem.get_history(session_id)
        if not raw:
            raise HTTPException(status_code=404, detail=f"No history for session {session_id}")
        s_id = raw[0]["student_id"]
        messages = [
            HistoryMessage(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                intent=r.get("intent"),
                tools_used=json.loads(r["tools_used"]) if r.get("tools_used") else None,
                timestamp=r["created_at"],
            )
            for r in raw
        ]
        return ChatHistoryResponse(
            session_id=session_id,
            student_id=s_id,
            total_messages=len(messages),
            messages=messages,
        )

    sessions = mem.get_all_sessions(student_id=student_id)
    if not sessions:
        raise HTTPException(status_code=404, detail=f"No history for student {student_id}")
    latest = sessions[0]["session_id"]
    raw = mem.get_history(latest)
    messages = [
        HistoryMessage(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            intent=r.get("intent"),
            tools_used=json.loads(r["tools_used"]) if r.get("tools_used") else None,
            timestamp=r["created_at"],
        )
        for r in raw
    ]
    return ChatHistoryResponse(
        session_id=latest,
        student_id=student_id,
        total_messages=len(messages),
        messages=messages,
    )


@router.delete("/history", status_code=200)
async def delete_history(session_id: str = Query(...)):
    deleted = mem.delete_session(session_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No history for session {session_id}")
    return {"deleted": deleted, "session_id": session_id}


@router.get("/sessions")
async def list_sessions(student_id: Optional[str] = Query(None)):
    sessions = mem.get_all_sessions(student_id=student_id)
    return {"sessions": sessions, "total": len(sessions)}
