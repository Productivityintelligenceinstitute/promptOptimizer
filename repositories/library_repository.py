from schemas.library_model import LibraryModel
from schemas.user_model import UserModel
from schemas.messages_model import MessagesModel
from uuid import UUID

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
        try:
            user_uuid = UUID(str(user_id))
        except ValueError:
            raise ValueError("Invalid user_id")

        page = max(page, 1)
        size = min(max(size, 1), 100)

        base_query = (
            db.query(
                MessagesModel.id.label("message_id"),
                MessagesModel.content,
                LibraryModel.created_at.label("added_at")
            )
            .select_from(LibraryModel)
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.id)
            .filter(LibraryModel.user_id == user_uuid)
        )

        if search:
            search = search.strip()
            base_query = base_query.filter(MessagesModel.content.ilike(f"%{search}%"))

        total = base_query.order_by(None).count()

        records = (
            base_query
            .order_by(LibraryModel.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = [
            {
                "message_id": r.message_id,
                "content": r.content,
                "added_at": r.added_at
            }
            for r in records
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