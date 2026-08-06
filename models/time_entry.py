from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TimeEntry(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    task_id: UUID
    date: date
    hours: float
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("hours")
    @classmethod
    def hours_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("hours must be greater than 0")
        if v > 24:
            raise ValueError("hours cannot exceed 24 per entry")
        return v
