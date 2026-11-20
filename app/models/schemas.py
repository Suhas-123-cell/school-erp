from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    student_id: Optional[str] = Field(default="S001", description="Student ID")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation continuity")


class ToolCallRecord(BaseModel):
    """A tool call the agent actually made, with the arguments after validation."""

    name: str
    arguments: Dict[str, Any] = {}
    status: str = Field(description="ok, tool_error, invalid_arguments or unknown_tool")
    error: Optional[str] = None


class ChatResponse(BaseModel):
    intent: str
    response: str
    status: str = Field(description="Fetched/Generated/Calculated/Answered on success, 'error' on failure")
    tools_used: List[str] = []
    tool_calls: List[ToolCallRecord] = []
    error: Optional[str] = Field(default=None, description="Error code when status is 'error'")
    error_detail: Optional[str] = None
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
