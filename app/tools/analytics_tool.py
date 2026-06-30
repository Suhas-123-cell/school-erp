import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path("mock_data")


def _load(name: str) -> dict:
    with open(DATA_PATH / f"{name}.json") as f:
        return json.load(f)


def get_academic_summary(student_id: str) -> Dict[str, Any]:
    try:
        attendance_data = _load("attendance").get(student_id, {})
        marks_data = _load("marks").get(student_id, {})
        fees_data = _load("fees").get(student_id, {})
        hw_data = _load("homework")
        students_data = _load("students")
        student = students_data.get(student_id, {})
        cls = student.get("class", "")
        hw_list = hw_data.get(cls, [])
    except Exception as e:
        return {"error": str(e)}

    subjects = marks_data.get("subjects", {})
    all_mid = [v["mid_term"] for v in subjects.values() if v.get("mid_term")]
    avg = round(sum(all_mid) / len(all_mid), 2) if all_mid else 0

    sorted_subs = sorted(subjects.items(), key=lambda x: x[1].get("mid_term", 0), reverse=True)
    strong = [s[0] for s in sorted_subs[:2]]
    weak = [s[0] for s in sorted_subs[-2:]]

    overall_att = attendance_data.get("overall", {}).get("percentage", 0)
    current_month = datetime.now().strftime("%Y-%m")
    monthly = attendance_data.get("monthly", {}).get(current_month, [])
    m_total = len(monthly)
    m_present = sum(1 for r in monthly if r["status"] == "present")
    m_pct = round(m_present / m_total * 100, 2) if m_total else 0

    pending_hw = [h for h in hw_list if h["status"] == "pending"]
    fees = fees_data or {}

    grade = "A+" if avg >= 90 else "A" if avg >= 80 else "B+" if avg >= 70 else "B" if avg >= 60 else "C"

    return {
        "student_name": student.get("name", ""),
        "class": cls,
        "overall_grade": grade,
        "academic_average": avg,
        "strong_subjects": strong,
        "weak_subjects": weak,
        "subject_scores": {k: v["mid_term"] for k, v in subjects.items()},
        "overall_attendance": overall_att,
        "current_month_attendance": m_pct,
        "pending_homework_count": len(pending_hw),
        "fee_status": "Cleared" if fees.get("pending_amount", 1) == 0 else f"₹{fees.get('pending_amount', 0)} pending",
        "semester": marks_data.get("semester", ""),
        "performance_status": "Excellent" if avg >= 85 else "Good" if avg >= 70 else "Needs Improvement",
    }


def get_recommendations(student_id: str) -> Dict[str, Any]:
    summary = get_academic_summary(student_id)
    if "error" in summary:
        return summary

    weak_subs = summary["weak_subjects"]
    strong_subs = summary["strong_subjects"]
    avg = summary["academic_average"]
    att = summary["overall_attendance"]
    scores = summary.get("subject_scores", {})

    suggestions = []
    priority_actions = []

    for sub in weak_subs:
        score = scores.get(sub, 0)
        if score < 75:
            suggestions.append(f"Focus heavily on {sub} — current score {score}/100. Consider extra coaching.")
            priority_actions.append(f"Revise {sub} chapters 1-3 this week")
        else:
            suggestions.append(f"Moderate improvement needed in {sub} (score: {score}/100). Practice more exercises.")

    if att < 85:
        suggestions.append(f"Attendance is {att}% — aim for 90%+ to avoid shortage. Attend all remaining classes.")
        priority_actions.append("Maintain 100% attendance for the rest of the semester")

    if avg < 75:
        suggestions.append("Consider forming a study group with classmates for collaborative learning.")
        suggestions.append("Spend at least 2 hours daily on academics.")

    for sub in strong_subs:
        suggestions.append(f"Excellent in {sub}! Consider participating in competitions or Olympiads.")

    return {
        "student_name": summary["student_name"],
        "current_average": avg,
        "attendance": att,
        "weak_subjects": weak_subs,
        "strong_subjects": strong_subs,
        "recommendations": suggestions,
        "priority_actions": priority_actions,
        "study_tip": "Dedicate 45-minute focused study sessions per subject with 10-minute breaks.",
        "target_average": min(avg + 10, 100),
    }


def get_attendance_insights(student_id: str, target_percentage: float = 90.0) -> Dict[str, Any]:
    try:
        att_data = _load("attendance").get(student_id, {})
    except Exception as e:
        return {"error": str(e)}

    overall = att_data.get("overall", {})
    attended = overall.get("attended", 0)
    total = overall.get("total_classes", 0)
    current_pct = overall.get("percentage", 0)

    remaining_classes = 45
    classes_to_attend_for_target = max(0, int(target_percentage / 100 * (total + remaining_classes)) - attended)
    max_absences_allowed = remaining_classes - classes_to_attend_for_target

    if_all_present = round((attended + remaining_classes) / (total + remaining_classes) * 100, 2)
    if_all_absent = round(attended / (total + remaining_classes) * 100, 2)

    return {
        "student_name": att_data.get("name", ""),
        "current_attendance": current_pct,
        "target_attendance": target_percentage,
        "classes_attended": attended,
        "total_classes_so_far": total,
        "estimated_remaining_classes": remaining_classes,
        "can_achieve_target": classes_to_attend_for_target <= remaining_classes,
        "classes_needed_for_target": classes_to_attend_for_target,
        "max_absences_allowed": max(0, max_absences_allowed),
        "attendance_if_perfect": if_all_present,
        "attendance_if_all_absent": if_all_absent,
        "recommendation": (
            f"You need to attend at least {classes_to_attend_for_target} of the remaining {remaining_classes} classes to reach {target_percentage}%."
            if classes_to_attend_for_target <= remaining_classes
            else f"Achieving {target_percentage}% is not possible even with perfect attendance. Focus on maximizing attendance."
        ),
    }


def get_parent_report(student_id: str) -> Dict[str, Any]:
    summary = get_academic_summary(student_id)
    recommendations = get_recommendations(student_id)
    attendance_insights = get_attendance_insights(student_id)

    try:
        hw_data = _load("homework")
        students = _load("students")
        cls = students.get(student_id, {}).get("class", "")
        hw_list = hw_data.get(cls, [])
        pending_hw = [h for h in hw_list if h["status"] == "pending"]
        fees_data = _load("fees").get(student_id, {})
    except Exception as e:
        return {"error": str(e)}

    return {
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "student_name": summary.get("student_name", ""),
        "class": summary.get("class", ""),
        "attendance_summary": {
            "overall_percentage": summary.get("overall_attendance"),
            "current_month": summary.get("current_month_attendance"),
            "status": "Good" if summary.get("overall_attendance", 0) >= 85 else "Needs Attention",
        },
        "academic_performance": {
            "overall_grade": summary.get("overall_grade"),
            "average_score": summary.get("academic_average"),
            "strong_subjects": summary.get("strong_subjects"),
            "weak_subjects": summary.get("weak_subjects"),
            "performance_status": summary.get("performance_status"),
        },
        "homework_status": {
            "pending_count": len(pending_hw),
            "pending_subjects": [h["subject"] for h in pending_hw],
        },
        "fee_status": {
            "paid": fees_data.get("paid_amount", 0),
            "pending": fees_data.get("pending_amount", 0),
            "due_date": fees_data.get("due_date"),
            "status": "Cleared" if fees_data.get("pending_amount", 1) == 0 else "Pending",
        },
        "ai_suggestions": recommendations.get("recommendations", [])[:3],
        "priority_actions": recommendations.get("priority_actions", []),
    }
