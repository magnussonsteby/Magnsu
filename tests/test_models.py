import uuid

import pytest
from pydantic import ValidationError

from models import Project, Task, Team, User
from models.enums import ProjectStatus, TaskPriority, TaskStatus, UserRole


def test_user_valid():
    user = User(name="Alice", email="alice@example.com", role=UserRole.admin)
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.role == "admin"
    assert user.id is not None
    assert user.created_at is not None


def test_user_invalid_email():
    with pytest.raises(ValidationError):
        User(name="Alice", email="not-an-email", role=UserRole.admin)


def test_user_missing_email():
    with pytest.raises(ValidationError):
        User(name="Alice", role=UserRole.admin)


def test_team_member_ids_default_empty():
    team = Team(name="Eng", owner_id=uuid.uuid4())
    assert team.member_ids == []


def test_project_status_defaults_to_draft():
    project = Project(name="Test", team_id=uuid.uuid4())
    assert project.status == "draft"
    assert project.description is None


def test_project_custom_status():
    project = Project(name="Test", team_id=uuid.uuid4(), status=ProjectStatus.active)
    assert project.status == "active"


def test_task_defaults():
    task = Task(title="Do something", project_id=uuid.uuid4())
    assert task.status == "todo"
    assert task.priority == "medium"
    assert task.assignee_id is None


def test_task_all_fields():
    pid = uuid.uuid4()
    uid = uuid.uuid4()
    task = Task(
        title="Fix bug",
        description="Critical fix",
        project_id=pid,
        assignee_id=uid,
        status=TaskStatus.in_progress,
        priority=TaskPriority.high,
    )
    assert task.description == "Critical fix"
    assert task.status == "in_progress"
    assert task.priority == "high"
    assert task.assignee_id == uid


def test_task_missing_project_id():
    with pytest.raises(ValidationError):
        Task(title="T")
