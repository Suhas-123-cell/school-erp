"""Service layer for timetable data access."""
from app.tools.timetable_tool import get_timetable as _get_timetable

def fetch_timetable(student_id: str, day: str = None, subject: str = None):
    return _get_timetable(student_id=student_id, day=day, subject=subject)
