from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import database
from models import library_model

from services.ibrary_service import (
        add_to_library_service, 
        get_library_service, 
        my_library_service, 
        remove_from_library_service
    )

library_router = APIRouter(prefix="/library")

@library_router.get("")
async def get_library(user_id: str, db: Session = Depends(database.get_db)):
    return get_library_service(user_id, db)

@library_router.get("/me")
async def my_library(user_id: str, db: Session = Depends(database.get_db)):
    return my_library_service(user_id, db)

@library_router.post("/add")
async def add_to_library(payload: library_model.AddToLibraryRequest, db: Session = Depends(database.get_db)):
    return add_to_library_service(payload, db)

@library_router.delete("/remove")
async def remove_from_library(payload: library_model.RemoveFromLibraryQuery, db: Session = Depends(database.get_db)):
    return remove_from_library_service(payload, db)