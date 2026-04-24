from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import UserDB
from db.session import get_db
from api.schemas import UserCreate, UserOut

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
