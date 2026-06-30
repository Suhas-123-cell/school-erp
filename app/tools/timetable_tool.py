import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

DATA_PATH = Path("mock_data")
STUDENTS_PATH = Path("mock_data/students.json")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _load_tt() -> dict:
    with open(DATA_PATH / "timetable.json") as f:
        return json.load(f)


def _student_class(student_id: str) -> Optional[str]:
    with open(STUDENTS_PATH) as f:
        students = json.load(f)
    return students.get(student_id, {}).get("class")


def _current_day() -> str:
    return DAYS[datetime.now().weekday()]


def get_timetable(
    student_id: str,
    day: Optional[str] = None,
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    cls = _student_class(student_id)
    if not cls:
        return {"error": f"Student {student_id} not found"}

    tt_data = _load_tt()
    class_tt = tt_data.get(cls, {})

    if not class_tt:
        return {"error": f"No timetable found for class {cls}"}

    today = _current_day()
    tomorrow_day = DAYS[(datetime.now().weekday() + 1) % 7]

    if day:
        day = day.capitalize()
        if day not in class_tt:
            return {"error": f"No timetable for {day}. School may be closed.", "available_days": list(class_tt.keys())}
        periods = class_tt[day]
        real_periods = [p for p in periods if isinstance(p["period"], int)]
        return {
            "class": cls,
            "day": day,
            "periods": periods,
            "total_periods": len(real_periods),
            "first_class": real_periods[0] if real_periods else None,
            "last_class": real_periods[-1] if real_periods else None,
        }

    if subject:
        results = []
        for d, periods in class_tt.items():
            for p in periods:
                if isinstance(p["period"], int) and p["subject"].lower() == subject.lower():
                    results.append({"day": d, **p})
        return {
            "class": cls,
            "subject": subject,
            "schedule": results,
            "total_classes_per_week": len(results),
        }

    today_periods = class_tt.get(today, [])
    tomorrow_periods = class_tt.get(tomorrow_day, [])
    real_today = [p for p in today_periods if isinstance(p["period"], int)]
    now = datetime.now().strftime("%H:%M")
    current_class = next(
        (p for p in real_today if p["time"].split("-")[0] <= now <= p["time"].split("-")[1]),
        None,
    )
    next_class = next(
        (p for p in real_today if p["time"].split("-")[0] > now),
        None,
    )

    return {
        "class": cls,
        "today": today,
        "today_schedule": today_periods,
        "tomorrow": tomorrow_day,
        "tomorrow_schedule": tomorrow_periods,
        "current_class": current_class,
        "next_class": next_class,
        "total_periods_today": len(real_today),
    }
