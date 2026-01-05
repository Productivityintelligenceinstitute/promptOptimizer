from sqlalchemy.orm import Session

from repositories.library_repository import LibraryRepository
from repositories.check_role import RoleRepository
from repositories.check_access import AccessRepository

from core.exceptions.authorization import AuthorizationException
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException

def get_library_service(user_id, db: Session):
    role = RoleRepository.check_role(db, user_id)
    
    if role != "admin":
        access = AccessRepository.check_access(db, user_id, "LIB")
        if not access:
            raise AuthorizationException("Library access denied")
    
    return LibraryRepository.get_all_entries(db)

def my_library_service(user_id, db: Session):
    return LibraryRepository.get_by_user(user_id, db)

def add_to_library_service(payload, db: Session):
    if LibraryRepository.exist(payload.user_id, payload.message_id, db):
        raise ConflictException("Message already in library")
    
    LibraryRepository.add(payload.user_id, payload.message_id, db)
    return {"status": "Message added to library successfully"}

def remove_from_library_service(message_id, db: Session):
    if not LibraryRepository.delete(db, message_id):
        raise NotFoundException("Message not found in library")
    
    return {"detail": "Message removed from library successfully"}