from fastapi import HTTPException
from sqlalchemy.orm import Session

from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository

from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate

from core.exceptions.not_found import NotFoundException

def get_chat_list_service(user_id, db: Session):
    chats = ChatRepository.get_chats_by_user(user_id, db)
    
    if not chats:
        return {"chats": []}
    
    return {"chats": chats}

def get_chat_messages_service(chat_id, db: Session):
    messages = MessageRepository.get_chat_messages(db, chat_id)
    paginated = sqlalchemy_paginate(messages)
    
    return paginated

def delete_chat_service(payload, db: Session):
    try:
        ChatRepository.delete_chat(payload.user_id, payload.chat_id, db)
        return {"detail": "Chat deleted successfully"}
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., 404 Chat not found) directly
        raise
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)