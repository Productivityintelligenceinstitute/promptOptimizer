from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session
from database import database

from models.update_role_model import UpdateRoleRequestModel
from services.update_user_role_service import update_user_role_service

update_role_router = APIRouter()

@update_role_router.put("/update-role")
async def update_user_role(payload: UpdateRoleRequestModel, db: Session = Depends(database.get_db)):
    return update_user_role_service(payload, db)