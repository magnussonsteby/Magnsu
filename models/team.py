from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Team(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    owner_id: UUID
    member_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
