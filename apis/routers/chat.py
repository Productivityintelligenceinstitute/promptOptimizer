from fastapi import APIRouter, Depends
from fastapi_pagination import Page
from sqlalchemy.orm import Session

from models import models, chat_model
from database import database

from services.chat_service import (
        get_chat_list_service,
        get_chat_messages_service,
        delete_chat_service
    )

chat_router = APIRouter()

@chat_router.get("/chat-list")
async def get_chat_list(user_id: str, db: Session = Depends(database.get_db)):
    return get_chat_list_service(user_id, db)

@chat_router.get("/chat-messages/{chat_id}", response_model= Page[models.MessageOut])
async def get_chat_messages(chat_id: str, db: Session = Depends(database.get_db)):
    return get_chat_messages_service(chat_id, db)

@chat_router.delete("/delete-chat/{chat_id}")
async def delete_chat(input: chat_model.RemoveChat, db: Session = Depends(database.get_db)):
    return delete_chat_service(input.user_id, input.chat_id, db)
