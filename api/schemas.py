from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from models.enums import ProjectStatus, TaskPriority, TaskStatus, UserRole


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: UserRole


class TeamCreate(BaseModel):
    name: str
    owner_id: str


class TeamAddMember(BaseModel):
    user_id: str


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.draft
    team_id: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.medium
    project_id: str
    assignee_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: str
    created_at: datetime


class TeamOut(BaseModel):
    id: str
    name: str
    owner_id: str
    member_ids: list[str]
    created_at: datetime

    @classmethod
    def from_db(cls, team) -> "TeamOut":
        return cls(
            id=team.id,
            name=team.name,
            owner_id=team.owner_id,
            member_ids=[m.id for m in team.members],
            created_at=team.created_at,
        )


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    status: str
    team_id: str
    created_at: datetime
    updated_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    project_id: str
    assignee_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TimeEntryCreate(BaseModel):
    user_id: str
    task_id: str
    date: date
    hours: float
    notes: Optional[str] = None


class TimeEntryUpdate(BaseModel):
    hours: Optional[float] = None
    notes: Optional[str] = None


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    task_id: str
    date: date
    hours: float
    notes: Optional[str]
    created_at: datetime
