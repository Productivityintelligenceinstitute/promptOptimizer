from fastapi import APIRouter, Depends, HTTPException
from fastapi_pagination import Page
from sqlalchemy.orm import Session
from uuid import UUID as UUIDType

from models import models, chat_model
from database import database
from schemas.user_model import UserModel

from services.chat_service import (
        get_chat_list_service,
        get_chat_messages_service,
        delete_chat_service
    )

chat_router = APIRouter()

@chat_router.get("/chat-list")
async def get_chat_list(user_id: str, db: Session = Depends(database.get_db)):
    # user_id might be a Firebase UID, need to convert to user UUID
    try:
        user_uuid = UUIDType(user_id)
        # If it's a valid UUID, use it directly
        return get_chat_list_service(user_uuid, db)
    except ValueError:
        # If not a valid UUID, treat it as Firebase UID and look up the user
        user = db.query(UserModel).filter(UserModel.firebase_uid == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return get_chat_list_service(user.id, db)

@chat_router.get("/chat-messages/{chat_id}", response_model= Page[models.MessageOut])
async def get_chat_messages(chat_id: str, db: Session = Depends(database.get_db)):
    # Validate chat_id is a valid UUID
    if not chat_id or chat_id == "undefined" or chat_id == "null":
        raise HTTPException(status_code=400, detail="Invalid chat_id: chat_id is required and must be a valid UUID")
    
    try:
        chat_uuid = UUIDType(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid chat_id format: '{chat_id}' is not a valid UUID")
    
    return get_chat_messages_service(chat_uuid, db)

@chat_router.delete("/delete-chat/remove/{user_id}/{chat_id}")
async def delete_chat(payload: chat_model.RemoveChat, db: Session = Depends(database.get_db)):
    return delete_chat_service(payload, db)
