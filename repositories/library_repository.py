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
    def get_all_entries_paginated(db, page: int, size: int, search: str | None = None):
        base_query = (
            db.query(
                UserModel.email,
                MessagesModel.id,
                MessagesModel.content,
                LibraryModel.created_at
            )
            .select_from(LibraryModel)
            .join(UserModel, LibraryModel.user_id == UserModel.id)
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.id)
            .order_by(LibraryModel.created_at.desc())
        )

        if search:
            like = f"%{search}%"
            base_query = base_query.filter(MessagesModel.content.ilike(like))

        total = base_query.count()

        library_entries = (
            base_query
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        
        items = [
            {
                "email": email,
                "message_id": msg_id,
                "content": content,
                "created_at": created_at,
            }
            for email, msg_id, content, created_at in library_entries
        ]

        return items, total
    
    @staticmethod
    def get_by_user_paginated(user_id, db, page: int, size: int, search: str | None = None):
        base_query = (
            db.query(
                MessagesModel.id,
                MessagesModel.content,
                LibraryModel.created_at
            )
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.id)
            .filter(LibraryModel.user_id == user_id)
            .order_by(LibraryModel.created_at.desc())
        )

        if search:
            like = f"%{search}%"
            base_query = base_query.filter(MessagesModel.content.ilike(like))

        total = base_query.count()

        records = (
            base_query
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = [
            {
                "message_id": msg_id,
                "content": content,
                "added_at": created_at
            }
            for msg_id, content, created_at in records
        ]

        return items, total
    
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