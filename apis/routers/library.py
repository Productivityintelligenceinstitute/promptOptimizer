from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID as UUIDType

from database import database
from models import library_model
from schemas.user_model import UserModel

from services.ibrary_service import (
        add_to_library_service, 
        get_library_service, 
        my_library_service, 
        remove_from_library_service
    )

library_router = APIRouter(prefix="/library")

def _get_user_uuid(user_id: str, db: Session):
    """Convert Firebase UID to user UUID, or return UUID if already valid UUID."""
    try:
        user_uuid = UUIDType(user_id)
        # If it's a valid UUID, use it directly
        return user_uuid
    except ValueError:
        # If not a valid UUID, treat it as Firebase UID and look up the user
        user = db.query(UserModel).filter(UserModel.firebase_uid == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user.id

@library_router.get("")
async def get_library(
    user_id: str,
    page: int = 1,
    size: int = 10,
    q: str | None = None,
    db: Session = Depends(database.get_db),
):
    user_uuid = _get_user_uuid(user_id, db)
    return get_library_service(user_uuid, db, page, size, q)

@library_router.get("/me")
async def my_library(
    user_id: str,
    page: int = 1,
    size: int = 50,
    q: str | None = None,
    db: Session = Depends(database.get_db),
):
    user_uuid = _get_user_uuid(user_id, db)
    return my_library_service(user_uuid, db, page, size, q)

@library_router.post("/add")
async def add_to_library(payload: library_model.AddToLibraryRequest, db: Session = Depends(database.get_db)):
    return add_to_library_service(payload, db)

@library_router.delete("/remove/{message_id}")
async def remove_from_library(
    message_id: str,
    user_id: str,
    db: Session = Depends(database.get_db),
):
    user_uuid = _get_user_uuid(user_id, db)
    return remove_from_library_service(message_id, user_uuid, db)