import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/students", tags=["Students"])
DATA_PATH = Path("mock_data/students.json")


class StudentIn(BaseModel):
    name: str
    student_class: str
    roll_number: int
    section: str
    gender: str
    dob: str
    email: Optional[str] = ""
    parent: str
    parent_email: Optional[str] = ""
    phone: Optional[str] = ""
    admission_date: str = Field(default_factory=lambda: date.today().isoformat())


def _load() -> dict:
    with open(DATA_PATH) as f:
        return json.load(f)

def _save(data: dict) -> None:
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


@router.get("")
async def list_students():
    students = _load()
    return [{"student_id": k, **v} for k, v in students.items()]


@router.post("", status_code=201)
async def add_student(payload: StudentIn):
    students = _load()
    existing = [int(k[1:]) for k in students if k.startswith("S") and k[1:].isdigit()]
    next_id = f"S{(max(existing) + 1 if existing else 1):03d}"
    if next_id in students:
        raise HTTPException(409, f"{next_id} already exists")

    students[next_id] = {
        "name": payload.name,
        "class": payload.student_class,
        "roll_number": payload.roll_number,
        "parent": payload.parent,
        "parent_email": payload.parent_email or "",
        "email": payload.email or "",
        "phone": payload.phone or "",
        "dob": payload.dob,
        "admission_date": payload.admission_date,
        "section": payload.section,
        "gender": payload.gender,
    }
    _save(students)
    return {"student_id": next_id, **students[next_id]}


@router.delete("/{student_id}", status_code=204)
async def delete_student(student_id: str):
    students = _load()
    if student_id not in students:
        raise HTTPException(404, f"{student_id} not found")
    del students[student_id]
    _save(students)
