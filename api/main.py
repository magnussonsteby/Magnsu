from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse

from db.base import Base, engine
from api.routers import users, teams, projects, tasks, time_entries


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Magnsu API", version="0.1.0", lifespan=lifespan)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(teams.router, prefix="/teams", tags=["teams"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(time_entries.router, prefix="/time-entries", tags=["time-entries"])


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_ui():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())
