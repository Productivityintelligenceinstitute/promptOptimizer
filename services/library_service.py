from fastapi import HTTPException
from sqlalchemy.orm import Session

from repositories.library_repository import LibraryRepository
from repositories.check_role import RoleRepository
from repositories.check_access import AccessRepository

from core.exceptions.authorization import AuthorizationException
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException

def get_library_service(user_id, db: Session, page: int, size: int, search: str | None = None):
    try:
        role = RoleRepository.check_role(db, user_id)
        
        if role != "admin":
            items, total = LibraryRepository.get_by_user_paginated(user_id, db, page, size, search)
            pages = (total + size - 1) // size
            return {
                "items": items,
                "total": total,
                "page": page,
                "size": size,
                "pages": pages
            }
        
        items, total = LibraryRepository.get_all_entries_paginated(db, page, size, search)
        pages = (total + size - 1) // size
        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages
        }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

def my_library_service(user_id, db: Session, page: int, size: int, search: str | None = None):
    items, total = LibraryRepository.get_by_user_paginated(user_id, db, page, size, search)
    pages = (total + size - 1) // size
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

def add_to_library_service(payload, db: Session):
    try:
        # Prevent duplicate entries for same user + message
        if LibraryRepository.exist(payload.user_id, payload.message_id, db):
            raise ConflictException("Message already in library")
        
        LibraryRepository.add(payload.user_id, payload.message_id, db)
        return {"status": "Message added to library successfully"}
    except ConflictException as e:
        # Surface proper 409 to the client so it can show \"already shared\"
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

def remove_from_library_service(message_id, user_id, db: Session):
    try:
        role = RoleRepository.check_role(db, user_id)
        if role != "admin":
            raise AuthorizationException("Only admin can remove library entries")

        if not LibraryRepository.delete(db, message_id):
            raise NotFoundException("Message not found in library")
        
        return {"detail": "Message removed from library successfully"}
    except (AuthorizationException, NotFoundException) as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)