import json
from pathlib import Path
from typing import Dict, Any

DATA_PATH = Path("mock_data")


def _load() -> dict:
    with open(DATA_PATH / "fees.json") as f:
        return json.load(f)


def get_fees(student_id: str) -> Dict[str, Any]:
    data = _load()
    if student_id not in data:
        return {"error": f"No fee records found for student ID {student_id}"}

    rec = data[student_id]
    paid_pct = round(rec["paid_amount"] / rec["annual_fee"] * 100, 2)

    return {
        "student_name": rec["name"],
        "class": rec["class"],
        "annual_fee": rec["annual_fee"],
        "paid_amount": rec["paid_amount"],
        "pending_amount": rec["pending_amount"],
        "paid_percentage": paid_pct,
        "due_date": rec.get("due_date"),
        "fee_structure": rec["fee_structure"],
        "payment_history": rec["payment_history"],
        "pending_dues": rec.get("pending_dues", []),
        "status": "Fully Paid" if rec["pending_amount"] == 0 else "Pending",
        "last_payment": rec["payment_history"][-1] if rec["payment_history"] else None,
    }
