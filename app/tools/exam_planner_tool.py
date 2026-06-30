"""Exam Preparation Planner — generates a day-by-day study schedule."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

DATA_PATH = Path("mock_data")


def _load(name: str) -> dict:
    with open(DATA_PATH / f"{name}.json") as f:
        return json.load(f)


def get_exam_plan(student_id: str, days_until_exam: int = 15) -> Dict[str, Any]:
    """Generate a personalised study plan based on marks performance."""
    try:
        marks_data = _load("marks").get(student_id, {})
        attendance_data = _load("attendance").get(student_id, {})
    except Exception as e:
        return {"error": str(e)}

    subjects = marks_data.get("subjects", {})
    if not subjects:
        return {"error": f"No marks data found for student {student_id}"}

    # Score each subject; lower score → more study hours needed
    scored = sorted(
        [(name, info.get("mid_term", 0)) for name, info in subjects.items()],
        key=lambda x: x[1]
    )

    total_weight = sum(max(100 - s, 10) for _, s in scored)
    total_hours = days_until_exam * 3  # 3 study hours per day

    subject_hours = {}
    for name, score in scored:
        weight = max(100 - score, 10)
        hours = round(weight / total_weight * total_hours)
        subject_hours[name] = max(hours, 1)

    # Build day-by-day plan
    today = datetime.now().date()
    plan = []
    subjects_cycle = [s[0] for s in scored]
    idx = 0

    for day_num in range(1, days_until_exam + 1):
        date = today + timedelta(days=day_num)
        day_label = date.strftime("%A, %d %b")

        if day_num == days_until_exam:
            plan.append({"day": day_num, "date": day_label, "focus": "Revision + Rest", "topics": "Quick revision of all subjects. No new topics.", "hours": 2})
        elif day_num % 7 == 0:
            plan.append({"day": day_num, "date": day_label, "focus": "Mock Test Day", "topics": "Full-length practice test across all subjects.", "hours": 3})
        else:
            sub = subjects_cycle[idx % len(subjects_cycle)]
            score = dict(scored)[sub]
            intensity = "Heavy focus" if score < 75 else "Moderate revision"
            plan.append({"day": day_num, "date": day_label, "focus": sub, "intensity": intensity, "hours": 3, "score": score})
            idx += 1

    all_scores = [s for _, s in scored]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    weak = [n for n, s in scored if s < 75]
    strong = [n for n, s in scored if s >= 85]

    return {
        "student_name": marks_data.get("name", ""),
        "exam_starts_in_days": days_until_exam,
        "exam_start_date": (today + timedelta(days=1)).strftime("%d %b %Y"),
        "overall_average": overall_avg,
        "weak_subjects": weak,
        "strong_subjects": strong,
        "subject_hours_allocation": subject_hours,
        "total_study_hours": sum(subject_hours.values()),
        "daily_plan": plan,
        "tips": [
            f"Prioritise {'and '.join(weak)} — these are your lowest scoring subjects." if weak else "All subjects are in good shape!",
            "Study in 45-minute sessions with 10-minute breaks (Pomodoro technique).",
            "Take a full-length mock test every 7 days to track progress.",
            "Get at least 8 hours of sleep — crucial for memory consolidation.",
        ],
    }
