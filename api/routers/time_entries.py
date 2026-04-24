from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import TaskDB, TimeEntryDB, UserDB
from db.session import get_db
from api.schemas import TimeEntryCreate, TimeEntryOut, TimeEntryUpdate

router = APIRouter()


def _validate_refs(db: Session, user_id: str, task_id: str) -> None:
    if not db.get(UserDB, user_id):
        raise HTTPException(404, "User not found")
    if not db.get(TaskDB, task_id):
        raise HTTPException(404, "Task not found")


@router.post("/", response_model=TimeEntryOut, status_code=201)
def create_time_entry(payload: TimeEntryCreate, db: Session = Depends(get_db)):
    if payload.hours <= 0 or payload.hours > 24:
        raise HTTPException(422, "hours must be between 0 and 24")
    _validate_refs(db, payload.user_id, payload.task_id)
    entry = TimeEntryDB(
        user_id=payload.user_id,
        task_id=payload.task_id,
        date=payload.date,
        hours=payload.hours,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/", response_model=list[TimeEntryOut])
def list_time_entries(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
):
    q = db.query(TimeEntryDB)
    if user_id:
        q = q.filter(TimeEntryDB.user_id == user_id)
    if task_id:
        q = q.filter(TimeEntryDB.task_id == task_id)
    if date_from:
        q = q.filter(TimeEntryDB.date >= date_from)
    if date_to:
        q = q.filter(TimeEntryDB.date <= date_to)
    return q.order_by(TimeEntryDB.date).all()


@router.get("/summary")
def hours_summary(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    db: Session = Depends(get_db),
):
    q = db.query(TimeEntryDB)
    if user_id:
        q = q.filter(TimeEntryDB.user_id == user_id)
    if task_id:
        q = q.filter(TimeEntryDB.task_id == task_id)
    if date_from:
        q = q.filter(TimeEntryDB.date >= date_from)
    if date_to:
        q = q.filter(TimeEntryDB.date <= date_to)
    total = q.with_entities(func.sum(TimeEntryDB.hours)).scalar() or 0.0
    count = q.count()
    return {"total_hours": total, "entry_count": count}


@router.get("/{entry_id}", response_model=TimeEntryOut)
def get_time_entry(entry_id: str, db: Session = Depends(get_db)):
    entry = db.get(TimeEntryDB, entry_id)
    if not entry:
        raise HTTPException(404, "Time entry not found")
    return entry


@router.patch("/{entry_id}", response_model=TimeEntryOut)
def update_time_entry(entry_id: str, payload: TimeEntryUpdate, db: Session = Depends(get_db)):
    entry = db.get(TimeEntryDB, entry_id)
    if not entry:
        raise HTTPException(404, "Time entry not found")
    if payload.hours is not None:
        if payload.hours <= 0 or payload.hours > 24:
            raise HTTPException(422, "hours must be between 0 and 24")
        entry.hours = payload.hours
    if payload.notes is not None:
        entry.notes = payload.notes
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_time_entry(entry_id: str, db: Session = Depends(get_db)):
    entry = db.get(TimeEntryDB, entry_id)
    if not entry:
        raise HTTPException(404, "Time entry not found")
    db.delete(entry)
    db.commit()
