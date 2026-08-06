from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .enums import UserRole


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class User(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    email: EmailStr
    role: UserRole
    created_at: datetime = Field(default_factory=_utcnow)
