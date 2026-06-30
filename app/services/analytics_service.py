"""Service layer for analytics, summaries, and AI recommendations."""
from app.tools.analytics_tool import (
    get_academic_summary,
    get_recommendations,
    get_attendance_insights,
    get_parent_report,
)

def fetch_academic_summary(student_id: str):
    return get_academic_summary(student_id=student_id)

def fetch_recommendations(student_id: str):
    return get_recommendations(student_id=student_id)

def fetch_attendance_insights(student_id: str, target_percentage: float = 90.0):
    return get_attendance_insights(student_id=student_id, target_percentage=target_percentage)

def fetch_parent_report(student_id: str):
    return get_parent_report(student_id=student_id)
