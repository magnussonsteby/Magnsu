from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import TeamDB, UserDB
from db.session import get_db
from api.schemas import TeamAddMember, TeamCreate, TeamOut, TeamUpdate

router = APIRouter()


@router.post("/", response_model=TeamOut, status_code=201)
def create_team(payload: TeamCreate, db: Session = Depends(get_db)):
    owner = db.get(UserDB, payload.owner_id)
    if not owner:
        raise HTTPException(404, "Owner user not found")
    team = TeamDB(name=payload.name, owner_id=payload.owner_id)
    team.members.append(owner)
    db.add(team)
    db.commit()
    db.refresh(team)
    return TeamOut.from_db(team)


@router.get("/", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db)):
    return [TeamOut.from_db(t) for t in db.query(TeamDB).all()]


@router.get("/{team_id}", response_model=TeamOut)
def get_team(team_id: str, db: Session = Depends(get_db)):
    team = db.get(TeamDB, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return TeamOut.from_db(team)


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(team_id: str, payload: TeamUpdate, db: Session = Depends(get_db)):
    team = db.get(TeamDB, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if payload.name is not None:
        team.name = payload.name
    db.commit()
    db.refresh(team)
    return TeamOut.from_db(team)


@router.delete("/{team_id}", status_code=204)
def delete_team(team_id: str, db: Session = Depends(get_db)):
    team = db.get(TeamDB, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    db.delete(team)
    db.commit()


@router.delete("/{team_id}/members/{user_id}", response_model=TeamOut)
def remove_member(team_id: str, user_id: str, db: Session = Depends(get_db)):
    team = db.get(TeamDB, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user in team.members:
        team.members.remove(user)
        db.commit()
        db.refresh(team)
    return TeamOut.from_db(team)


@router.post("/{team_id}/members", response_model=TeamOut)
def add_member(team_id: str, payload: TeamAddMember, db: Session = Depends(get_db)):
    team = db.get(TeamDB, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    user = db.get(UserDB, payload.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user not in team.members:
        team.members.append(user)
        db.commit()
        db.refresh(team)
    return TeamOut.from_db(team)
