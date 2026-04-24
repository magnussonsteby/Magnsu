from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import ProjectDB, TaskDB, TeamDB
from db.session import get_db
from api.schemas import TaskCreate, TaskOut, TaskUpdate

router = APIRouter()


def _assert_team_member(db: Session, project: ProjectDB, user_id: str) -> None:
    team = db.get(TeamDB, project.team_id)
    member_ids = {m.id for m in team.members} | {team.owner_id}
    if user_id not in member_ids:
        raise HTTPException(422, "Assignee must be a member of the project's team")


@router.post("/", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    project = db.get(ProjectDB, payload.project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if payload.assignee_id:
        _assert_team_member(db, project, payload.assignee_id)
    task = TaskDB(
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        project_id=payload.project_id,
        assignee_id=payload.assignee_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/", response_model=list[TaskOut])
def list_tasks(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(TaskDB)
    if project_id:
        q = q.filter(TaskDB.project_id == project_id)
    return q.all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(TaskDB, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(TaskDB, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.status is not None:
        task.status = payload.status.value
    if payload.priority is not None:
        task.priority = payload.priority.value
    if payload.assignee_id is not None:
        project = db.get(ProjectDB, task.project_id)
        _assert_team_member(db, project, payload.assignee_id)
        task.assignee_id = payload.assignee_id
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task
