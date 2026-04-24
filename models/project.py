from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import ProjectStatus


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Project(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.draft
    team_id: UUID
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
