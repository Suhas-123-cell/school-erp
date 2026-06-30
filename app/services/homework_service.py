"""Service layer for homework data access."""
from app.tools.homework_tool import get_homework as _get_homework

def fetch_homework(student_id: str, filter_by: str = "pending", subject: str = None):
    return _get_homework(student_id=student_id, filter_by=filter_by, subject=subject)
