from fastapi import HTTPException

from schemas.chat_model import ChatModel

class ChatRepository:
    @staticmethod
    def create_chat(db, user_id, title):
        new_chat = ChatModel(
            chat_title=title,
            user_id=user_id
        )
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat.id
    
    @staticmethod
    def get_chats_by_user(user_id, db):
        return (
            db.query(ChatModel)
            .filter(
                ChatModel.user_id == user_id
            )
            .order_by(
                ChatModel.created_at.desc()
            )
            .all()
        )
    
    @staticmethod
    def delete_chat(user_id, chat_id, db):
        chat = db.query(ChatModel).filter(
            ChatModel.id == chat_id,
            ChatModel.user_id == user_id
        ).first()

        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        db.delete(chat)
        db.commit()
