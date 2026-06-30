import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path("mock_data")
STUDENTS_PATH = Path("mock_data/students.json")


def _load_hw() -> dict:
    with open(DATA_PATH / "homework.json") as f:
        return json.load(f)


def _student_class(student_id: str) -> Optional[str]:
    with open(STUDENTS_PATH) as f:
        students = json.load(f)
    return students.get(student_id, {}).get("class")


def get_homework(
    student_id: str,
    filter_by: str = "pending",
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    cls = _student_class(student_id)
    if not cls:
        return {"error": f"Student {student_id} not found"}

    hw_data = _load_hw()
    assignments = hw_data.get(cls, [])

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    if filter_by == "today":
        assignments = [a for a in assignments if a["due_date"] == str(today)]
    elif filter_by == "tomorrow":
        assignments = [a for a in assignments if a["due_date"] == str(tomorrow)]
    elif filter_by == "pending":
        assignments = [a for a in assignments if a["status"] == "pending"]
    elif filter_by == "completed":
        assignments = [a for a in assignments if a["status"] == "completed"]
    elif filter_by == "overdue":
        assignments = [
            a for a in assignments
            if a["status"] == "pending" and datetime.strptime(a["due_date"], "%Y-%m-%d").date() < today
        ]

    if subject:
        assignments = [a for a in assignments if a["subject"].lower() == subject.lower()]

    overdue = [
        a for a in assignments
        if a.get("status") == "pending" and datetime.strptime(a["due_date"], "%Y-%m-%d").date() < today
    ]

    return {
        "student_class": cls,
        "filter": filter_by,
        "total": len(assignments),
        "overdue_count": len(overdue),
        "assignments": sorted(assignments, key=lambda x: x["due_date"]),
        "high_priority": [a for a in assignments if a.get("priority") == "high" and a["status"] == "pending"],
    }
