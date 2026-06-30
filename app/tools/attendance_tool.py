import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path("mock_data")


def _load() -> dict:
    with open(DATA_PATH / "attendance.json") as f:
        return json.load(f)


def get_attendance(
    student_id: str,
    month: Optional[str] = None,
    period: str = "month",
) -> Dict[str, Any]:
    data = _load()
    if student_id not in data:
        return {"error": f"No attendance records found for student ID {student_id}"}

    rec = data[student_id]
    today = datetime.now()
    target_month = month or today.strftime("%Y-%m")

    if period == "today":
        today_str = today.strftime("%Y-%m-%d")
        monthly = rec.get("monthly", {}).get(target_month, [])
        day_rec = next((r for r in monthly if r["date"] == today_str), None)
        return {
            "student_name": rec["name"],
            "date": today_str,
            "status": day_rec["status"] if day_rec else "No record",
            "reason": day_rec.get("reason") if day_rec else None,
        }

    if period == "week":
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        monthly = rec.get("monthly", {}).get(target_month, [])
        week_records = [
            r for r in monthly
            if datetime.strptime(r["date"], "%Y-%m-%d") >= week_start
        ]
        present = sum(1 for r in week_records if r["status"] == "present")
        return {
            "student_name": rec["name"],
            "week_start": week_start.strftime("%Y-%m-%d"),
            "records": week_records,
            "present": present,
            "absent": len(week_records) - present,
        }

    monthly_records = rec.get("monthly", {}).get(target_month, [])
    total = len(monthly_records)
    present = sum(1 for r in monthly_records if r["status"] == "present")
    absent = total - present
    percentage = round(present / total * 100, 2) if total else 0
    absent_dates = [r["date"] for r in monthly_records if r["status"] == "absent"]

    return {
        "student_name": rec["name"],
        "class": rec["class"],
        "month": target_month,
        "total_school_days": total,
        "days_present": present,
        "days_absent": absent,
        "attendance_percentage": percentage,
        "absent_dates": absent_dates,
        "overall_attendance_percentage": rec["overall"]["percentage"],
        "overall_attended": rec["overall"]["attended"],
        "overall_total": rec["overall"]["total_classes"],
        "status": "Good" if percentage >= 90 else ("Satisfactory" if percentage >= 75 else "Poor"),
    }
