from fastapi import APIRouter, HTTPException, status, Depends
from validator import validator
from database import database
from sqlalchemy.orm import Session
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from models.chat_model import ChatModel
from models.messages_model import MessagesModel

chat_router = APIRouter()


@chat_router.get("/chat-list")
async def get_chat_list(user_id: str, db: Session = Depends(database.get_db)):
    try:
        chats = db.query(ChatModel).filter(ChatModel.user_id == user_id).order_by(ChatModel.created_at.desc()).all()
        return {"chats": chats}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch chat list."
        )

@chat_router.get("/chat-messages/{chat_id}", response_model= Page[validator.MessageOut])
async def get_chat_messages(chat_id: str, db: Session = Depends(database.get_db)):
    try:
        # messages = (
        #     db.query(ChatModel, MessagesModel).join(MessagesModel, ChatModel.chat_id == MessagesModel.chat_id).filter(ChatModel.user_id == user_id, ChatModel.chat_id == chat_id).order_by(MessagesModel.created_at.desc()).all()
        # )
        messages = db.query(MessagesModel).filter(MessagesModel.chat_id == chat_id).order_by(MessagesModel.created_at.desc())
        
        paginated = sqlalchemy_paginate(messages)
        
        return paginated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch chat messages.{str(e)}"
        )

@chat_router.delete("/delete-chat/{chat_id}")
async def delete_chat(user_id: str, chat_id: str, db: Session = Depends(database.get_db)):
    try:
        db.query(ChatModel, MessagesModel).join(MessagesModel, ChatModel.chat_id == MessagesModel.chat_id).filter(ChatModel.user_id == user_id, ChatModel.chat_id == chat_id).delete(synchronize_session=False)
        # db.query(MessagesModel).filter(MessagesModel.chat_id == chat_id).delete()
        db.commit()
        db.query(ChatModel).filter(ChatModel.chat_id == chat_id).delete()
        db.commit()
        return {"detail": "Chat deleted successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat."
        )
