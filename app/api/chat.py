import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models.schemas import ChatRequest, ChatResponse, ChatHistoryResponse, HistoryMessage
from app.agents.erp_agent import run_agent
from app.memory import conversation_store as mem
from app.utils.logger import logger

import json

router = APIRouter(prefix="/chat", tags=["Chat"])


def _get_student_info(student_id: str) -> dict:
    import json
    from pathlib import Path
    try:
        with open("mock_data/students.json") as f:
            students = json.load(f)
        return students.get(student_id, {"name": "Student", "class": "10-A"})
    except Exception:
        return {"name": "Student", "class": "10-A"}


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    student_id = request.student_id or "S001"
    student_info = _get_student_info(student_id)
    if "name" not in student_info:
        raise HTTPException(status_code=404, detail=f"Student ID {student_id} not found")

    session_id = request.session_id or mem.generate_session_id()
    start = time.time()

    try:
        response_text, tools_used, intent = run_agent(
            message=request.message,
            student_id=student_id,
            session_id=session_id,
            student_name=student_info.get("name", "Student"),
            student_class=student_info.get("class", "10-A"),
        )
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=f"AI agent error: {str(e)}")

    exec_ms = round((time.time() - start) * 1000, 2)

    from app.agents.erp_agent import _build_execution_plan
    plan = _build_execution_plan(request.message, intent, tools_used)

    status_map = {
        "Attendance": "Fetched",
        "Marks & Grades": "Fetched",
        "Fee Status": "Fetched",
        "Homework": "Fetched",
        "Timetable": "Fetched",
        "Academic Summary": "Generated",
        "Recommendations": "Generated",
        "Attendance Insights": "Calculated",
        "Parent Report": "Generated",
        "General Query": "Answered",
    }
    base_intent = intent.split(" + ")[0] if " + " in intent else intent
    status = status_map.get(base_intent, "Completed")

    mem.save_message(session_id, student_id, "user", request.message)
    mem.save_message(session_id, student_id, "assistant", response_text,
                     intent=intent, tools_used=tools_used)

    return ChatResponse(
        intent=intent,
        response=response_text,
        status=status,
        tools_used=tools_used,
        execution_plan=plan,
        session_id=session_id,
        execution_time_ms=exec_ms,
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
