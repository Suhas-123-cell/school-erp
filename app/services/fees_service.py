"""Service layer for fee data access."""
from app.tools.fees_tool import get_fees as _get_fees

def fetch_fees(student_id: str):
    return _get_fees(student_id=student_id)
