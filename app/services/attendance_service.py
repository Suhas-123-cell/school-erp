"""Service layer for attendance data access."""
from app.tools.attendance_tool import get_attendance as _get_attendance

def fetch_attendance(student_id: str, month: str = None, period: str = "month"):
    return _get_attendance(student_id=student_id, month=month, period=period)
