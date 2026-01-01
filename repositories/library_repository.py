from schemas.library_model import LibraryModel
from schemas.user_model import UserModel
from schemas.messages_model import MessagesModel

class LibraryRepository:
    @staticmethod
    def exist(user_id, message_id, db):
        return db.query(LibraryModel).filter(
            LibraryModel.user_id == user_id,
            LibraryModel.message_id == message_id
        ).first() is not None
    
    @staticmethod
    def add(user_id, message_id, db):
        new_library_entry = LibraryModel(
            user_id=user_id,
            message_id=message_id
        )
        db.add(new_library_entry)
        db.commit()
        db.refresh(new_library_entry)
    
    @staticmethod
    def get_all_entries(db):
        library_entries = (
            db.query(
                UserModel.email,
                MessagesModel.content
            )
            .select_from(LibraryModel)
            .join(UserModel, LibraryModel.user_id == UserModel.id)
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.id)
            .order_by(LibraryModel.created_at.desc())
            .all()
        )
        
        return [
            {"email": email, "content": content}
            for email, content in library_entries
        ]
    
    @staticmethod
    def get_by_user(user_id, db):
        records = (
            db.query(
                MessagesModel.id,
                MessagesModel.content,
                LibraryModel.created_at
            )
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.id)
            .filter(LibraryModel.user_id == user_id)
            .order_by(LibraryModel.created_at.desc())
            .all()
        )

        return [
            {
                "message_id": msg_id,
                "content": content,
                "added_at": created_at
            }
            for msg_id, content, created_at in records
        ]
    
    @staticmethod
    def delete(db, message_id):
        entry = db.query(LibraryModel).filter(
            LibraryModel.message_id == message_id
        ).first()
        
        if not entry:
            return False
        
        db.delete(entry)
        db.commit()
        return True