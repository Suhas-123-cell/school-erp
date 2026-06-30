from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    student_id: Optional[str] = Field(default="S001", description="Student ID")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    intent: str
    response: str
    status: str
    tools_used: List[str] = []
    execution_plan: str = ""
    data: Optional[Dict[str, Any]] = None
    session_id: str
    execution_time_ms: float = 0.0


class HistoryMessage(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str] = None
    tools_used: Optional[List[str]] = None
    timestamp: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    student_id: str
    total_messages: int
    messages: List[HistoryMessage]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int
