from models import Project, Task, Team, User
from models.enums import ProjectStatus, TaskPriority, TaskStatus, UserRole

user = User(name="Alice", email="alice@example.com", role=UserRole.admin)
team = Team(name="Engineering", owner_id=user.id, member_ids=[user.id])
project = Project(name="API v2", team_id=team.id, status=ProjectStatus.active)
task = Task(
    title="Implement login",
    project_id=project.id,
    assignee_id=user.id,
    priority=TaskPriority.high,
    status=TaskStatus.in_progress,
)

print("User:", user.model_dump())
print()
print("Team:", team.model_dump())
print()
print("Project:", project.model_dump())
print()
print("Task:", task.model_dump())
print()
print("All models OK.")
