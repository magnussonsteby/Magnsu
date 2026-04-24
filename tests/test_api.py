import pytest


# --- helpers ---

def make_user(client, name, email, role="member"):
    res = client.post("/users/", json={"name": name, "email": email, "role": role})
    assert res.status_code == 201, res.text
    return res.json()


def make_team(client, name, owner_id):
    res = client.post("/teams/", json={"name": name, "owner_id": owner_id})
    assert res.status_code == 201, res.text
    return res.json()


def make_project(client, name, team_id, status="draft"):
    res = client.post("/projects/", json={"name": name, "team_id": team_id, "status": status})
    assert res.status_code == 201, res.text
    return res.json()


def make_task(client, title, project_id, **kwargs):
    res = client.post("/tasks/", json={"title": title, "project_id": project_id, **kwargs})
    assert res.status_code == 201, res.text
    return res.json()


# --- user tests ---

def test_create_user(client):
    user = make_user(client, "Alice", "alice@example.com", "admin")
    assert user["name"] == "Alice"
    assert user["role"] == "admin"
    assert "id" in user


def test_duplicate_email_rejected(client):
    make_user(client, "Alice", "dup@example.com")
    res = client.post("/users/", json={"name": "Bob", "email": "dup@example.com", "role": "member"})
    assert res.status_code == 409


def test_get_user(client):
    user = make_user(client, "Carol", "carol@example.com")
    res = client.get(f"/users/{user['id']}")
    assert res.status_code == 200
    assert res.json()["email"] == "carol@example.com"


def test_get_user_not_found(client):
    res = client.get("/users/nonexistent")
    assert res.status_code == 404


# --- team tests ---

def test_create_team_owner_auto_added_as_member(client):
    owner = make_user(client, "Owner", "owner@example.com", "admin")
    team = make_team(client, "Engineering", owner["id"])
    assert team["owner_id"] == owner["id"]
    assert owner["id"] in team["member_ids"]


def test_create_team_invalid_owner(client):
    res = client.post("/teams/", json={"name": "T", "owner_id": "bad-id"})
    assert res.status_code == 404


def test_add_team_member(client):
    owner = make_user(client, "O", "o@example.com", "admin")
    member = make_user(client, "M", "m@example.com")
    team = make_team(client, "T", owner["id"])
    res = client.post(f"/teams/{team['id']}/members", json={"user_id": member["id"]})
    assert res.status_code == 200
    assert member["id"] in res.json()["member_ids"]


def test_add_member_team_not_found(client):
    user = make_user(client, "U", "u@example.com")
    res = client.post("/teams/bad-team/members", json={"user_id": user["id"]})
    assert res.status_code == 404


# --- project tests ---

def test_create_project_defaults(client):
    owner = make_user(client, "Dev", "dev@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "API v2", team["id"])
    assert project["status"] == "draft"
    assert project["team_id"] == team["id"]


def test_create_project_team_not_found(client):
    res = client.post("/projects/", json={"name": "P", "team_id": "bad-id"})
    assert res.status_code == 404


def test_update_project_status(client):
    owner = make_user(client, "PO", "po@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "P", team["id"])
    res = client.patch(f"/projects/{project['id']}", json={"status": "active"})
    assert res.status_code == 200
    assert res.json()["status"] == "active"


# --- task tests ---

def test_create_task_unassigned(client):
    owner = make_user(client, "T1", "t1@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "P", team["id"])
    task = make_task(client, "Fix bug", project["id"])
    assert task["status"] == "todo"
    assert task["priority"] == "medium"
    assert task["assignee_id"] is None


def test_create_task_valid_assignee(client):
    owner = make_user(client, "T2", "t2@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "P", team["id"])
    task = make_task(client, "Do work", project["id"], assignee_id=owner["id"])
    assert task["assignee_id"] == owner["id"]


def test_create_task_non_member_assignee_rejected(client):
    owner = make_user(client, "T3", "t3@example.com", "admin")
    outsider = make_user(client, "Out", "outsider@example.com")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "P", team["id"])
    res = client.post("/tasks/", json={
        "title": "Task", "project_id": project["id"], "assignee_id": outsider["id"]
    })
    assert res.status_code == 422


def test_create_task_member_assignee_allowed(client):
    owner = make_user(client, "T4", "t4@example.com", "admin")
    member = make_user(client, "Mem", "mem@example.com")
    team = make_team(client, "T", owner["id"])
    client.post(f"/teams/{team['id']}/members", json={"user_id": member["id"]})
    project = make_project(client, "P", team["id"])
    task = make_task(client, "Task", project["id"], assignee_id=member["id"])
    assert task["assignee_id"] == member["id"]


def test_update_task_status(client):
    owner = make_user(client, "T5", "t5@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    project = make_project(client, "P", team["id"])
    task = make_task(client, "T", project["id"])
    res = client.patch(f"/tasks/{task['id']}", json={"status": "done"})
    assert res.status_code == 200
    assert res.json()["status"] == "done"


def test_list_tasks_filter_by_project(client):
    owner = make_user(client, "T6", "t6@example.com", "admin")
    team = make_team(client, "T", owner["id"])
    p1 = make_project(client, "P1", team["id"])
    p2 = make_project(client, "P2", team["id"])
    make_task(client, "Task A", p1["id"])
    make_task(client, "Task B", p2["id"])
    res = client.get(f"/tasks/?project_id={p1['id']}")
    assert res.status_code == 200
    titles = [t["title"] for t in res.json()]
    assert "Task A" in titles
    assert "Task B" not in titles
