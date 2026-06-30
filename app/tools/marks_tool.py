import json
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path("mock_data")


def _load() -> dict:
    with open(DATA_PATH / "marks.json") as f:
        return json.load(f)


def get_marks(
    student_id: str,
    subject: Optional[str] = None,
    exam_type: Optional[str] = None,
) -> Dict[str, Any]:
    data = _load()
    if student_id not in data:
        return {"error": f"No marks records found for student ID {student_id}"}

    rec = data[student_id]
    subjects = rec["subjects"]

    if subject:
        matched = next(
            (k for k in subjects if k.lower() == subject.lower()), None
        )
        if not matched:
            available = list(subjects.keys())
            return {"error": f"Subject '{subject}' not found. Available: {available}"}
        sub_data = subjects[matched]
        avg_ut = round(sum(sub_data["unit_tests"]) / len(sub_data["unit_tests"]), 2)
        avg_asn = round(sum(sub_data["assignments"]) / len(sub_data["assignments"]), 2)
        return {
            "student_name": rec["name"],
            "subject": matched,
            "teacher": sub_data["teacher"],
            "mid_term": sub_data["mid_term"],
            "unit_test_scores": sub_data["unit_tests"],
            "unit_test_average": avg_ut,
            "assignment_scores": sub_data["assignments"],
            "assignment_average": avg_asn,
            "grade": sub_data["grade"],
            "remarks": sub_data["remarks"],
            "max_marks": sub_data["max_marks"],
        }

    summary = []
    for name, sub in subjects.items():
        avg_ut = round(sum(sub["unit_tests"]) / len(sub["unit_tests"]), 2)
        summary.append({
            "subject": name,
            "mid_term": sub["mid_term"],
            "unit_test_average": avg_ut,
            "grade": sub["grade"],
            "teacher": sub["teacher"],
        })

    all_mid = [s["mid_term"] for s in subjects.values() if s["mid_term"] is not None]
    overall_avg = round(sum(all_mid) / len(all_mid), 2) if all_mid else 0
    best = max(summary, key=lambda x: x["mid_term"])
    worst = min(summary, key=lambda x: x["mid_term"])

    return {
        "student_name": rec["name"],
        "class": rec["class"],
        "semester": rec["semester"],
        "subjects": summary,
        "overall_average": overall_avg,
        "best_subject": best["subject"],
        "best_score": best["mid_term"],
        "weakest_subject": worst["subject"],
        "weakest_score": worst["mid_term"],
        "total_subjects": len(summary),
    }
