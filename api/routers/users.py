from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import UserDB
from db.session import get_db
from api.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()


@router.post("/", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.email == payload.email).first():
        raise HTTPException(409, "Email already registered")
    user = UserDB(name=payload.name, email=payload.email, role=payload.role.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(UserDB).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if payload.email is not None:
        existing = db.query(UserDB).filter(UserDB.email == payload.email, UserDB.id != user_id).first()
        if existing:
            raise HTTPException(409, "Email already registered")
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role.value
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
