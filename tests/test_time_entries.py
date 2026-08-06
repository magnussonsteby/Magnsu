from datetime import date


def make_user(client, name, email):
    res = client.post("/users/", json={"name": name, "email": email, "role": "member"})
    assert res.status_code == 201
    return res.json()


def make_task_setup(client):
    owner = make_user(client, "Owner", "owner_te@example.com")
    team = client.post("/teams/", json={"name": "T", "owner_id": owner["id"]}).json()
    project = client.post("/projects/", json={"name": "P", "team_id": team["id"]}).json()
    task = client.post("/tasks/", json={"title": "T", "project_id": project["id"]}).json()
    return owner, task


def test_create_time_entry(client):
    user, task = make_task_setup(client)
    res = client.post("/time-entries/", json={
        "user_id": user["id"], "task_id": task["id"],
        "date": "2026-01-01", "hours": 6.5,
    })
    assert res.status_code == 201
    data = res.json()
    assert data["hours"] == 6.5
    assert data["date"] == "2026-01-01"


def test_create_time_entry_with_notes(client):
    user, task = make_task_setup(client)
    res = client.post("/time-entries/", json={
        "user_id": user["id"], "task_id": task["id"],
        "date": "2026-01-02", "hours": 4, "notes": "Morning session",
    })
    assert res.status_code == 201
    assert res.json()["notes"] == "Morning session"


def test_hours_zero_rejected(client):
    user, task = make_task_setup(client)
    res = client.post("/time-entries/", json={
        "user_id": user["id"], "task_id": task["id"],
        "date": "2026-01-03", "hours": 0,
    })
    assert res.status_code == 422


def test_hours_over_24_rejected(client):
    user, task = make_task_setup(client)
    res = client.post("/time-entries/", json={
        "user_id": user["id"], "task_id": task["id"],
        "date": "2026-01-04", "hours": 25,
    })
    assert res.status_code == 422


def test_invalid_user_rejected(client):
    _, task = make_task_setup(client)
    res = client.post("/time-entries/", json={
        "user_id": "bad-id", "task_id": task["id"],
        "date": "2026-01-05", "hours": 4,
    })
    assert res.status_code == 404


def test_list_and_filter_by_task(client):
    user, task = make_task_setup(client)
    client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-02-01", "hours": 3})
    client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-02-02", "hours": 5})
    res = client.get(f"/time-entries/?task_id={task['id']}")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_summary(client):
    user, task = make_task_setup(client)
    client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-03-01", "hours": 3})
    client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-03-02", "hours": 5})
    res = client.get(f"/time-entries/summary?task_id={task['id']}")
    assert res.status_code == 200
    assert res.json()["total_hours"] == 8.0
    assert res.json()["entry_count"] == 2


def test_update_hours(client):
    user, task = make_task_setup(client)
    entry = client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-04-01", "hours": 4}).json()
    res = client.patch(f"/time-entries/{entry['id']}", json={"hours": 7})
    assert res.status_code == 200
    assert res.json()["hours"] == 7.0


def test_delete_time_entry(client):
    user, task = make_task_setup(client)
    entry = client.post("/time-entries/", json={"user_id": user["id"], "task_id": task["id"], "date": "2026-05-01", "hours": 2}).json()
    res = client.delete(f"/time-entries/{entry['id']}")
    assert res.status_code == 204
    assert client.get(f"/time-entries/{entry['id']}").status_code == 404
