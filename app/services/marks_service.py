"""Service layer for marks/grades data access."""
from app.tools.marks_tool import get_marks as _get_marks

def fetch_marks(student_id: str, subject: str = None, exam_type: str = None):
    return _get_marks(student_id=student_id, subject=subject, exam_type=exam_type)
