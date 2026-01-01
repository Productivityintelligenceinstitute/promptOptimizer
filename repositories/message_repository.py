from schemas.messages_model import MessagesModel

class MessageRepository:
    @staticmethod
    def add_user_message(db, chat_id, content):
        new_message = MessagesModel(
            chat_id=chat_id,
            role= "user",
            content=content
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
    
    @staticmethod
    def add_llm_message(db, chat_id, content):
        new_message = MessagesModel(
            chat_id=chat_id,
            role= "assistant",
            content=content
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
        return new_message.id
    
    @staticmethod
    def get_recent_messages(db, chat_id, limit=12):
        records = (
            db.query(MessagesModel)
            .filter(MessagesModel.chat_id == chat_id)
            .order_by(MessagesModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": r.role, "content": r.content}
            for r in reversed(records)
        ]
    
    @staticmethod
    def get_chat_messages(db, chat_id):
        return  (
            db.query(MessagesModel)
            .filter(
                MessagesModel.chat_id == chat_id
            )
            .order_by(
                MessagesModel.created_at.desc()
            )
        )