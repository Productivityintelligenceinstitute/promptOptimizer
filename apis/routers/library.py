from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import database
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.permission_model import PermissionModel
from schemas.subscription_model import SubscriptionsModel
from schemas.user_model import UserModel
from schemas.messages_model import MessagesModel
from schemas.library_model import LibraryModel
from uuid import uuid4
from database.db_utils import check_role, check_access

library_router = APIRouter()

@library_router.post("/add-to-library")
async def add_to_library(user_id: str, message_id: str, db: Session = Depends(database.get_db)):
    try:
        existing_entry = db.query(LibraryModel).filter(
            LibraryModel.user_id == user_id,
            LibraryModel.message_id == message_id
        ).first()
        
        if existing_entry:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message already in library."
            )
        
        new_library_entry = LibraryModel(
            library_id=str(uuid4()),
            user_id=user_id,
            message_id=message_id
        )
        db.add(new_library_entry)
        db.commit()
        db.refresh(new_library_entry)
        
        return {"detail": "Message added to library successfully."}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message to library.{str(e)}"
        )

@library_router.get("/get-library")
async def get_library(user_id: str, db: Session = Depends(database.get_db)):
    try:
        
        role = check_role(
            db= db, 
            user_id= user_id
        )
        
        if role == "admin":
            library_entries = (
                db.query(
                    UserModel.email,
                    MessagesModel.content
                )
                .select_from(LibraryModel)
                .join(UserModel, LibraryModel.user_id == UserModel.user_id)
                .join(MessagesModel, LibraryModel.message_id == MessagesModel.message_id)
                .order_by(LibraryModel.created_at.desc())
                .all()
            )
            
            results = []
            for email, content in library_entries:
                results.append({
                    "email": email,
                    "content": content
                })

            return results
        
        else:
            access = check_access (
                db= db,
                user_id= user_id,
                permission_name= "LIB"
            )
            
            if access:
                library_entries = (
                    db.query(
                        UserModel.email,
                        MessagesModel.content
                    )
                    .select_from(LibraryModel)
                    .join(UserModel, LibraryModel.user_id == UserModel.user_id)
                    .join(MessagesModel, LibraryModel.message_id == MessagesModel.message_id)
                    .order_by(LibraryModel.created_at.desc())
                    .all()
                )
                
                results = []
                for email, content in library_entries:
                    results.append({
                        "email": email,
                        "content": content
                    })

                return results
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have access to the library."
                )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve library.{str(e)}"
        )

@library_router.get("/my-library")
async def my_library(user_id: str, db: Session = Depends(database.get_db)):
    try:
        library_entries = (
            db.query(
                MessagesModel.message_id,
                MessagesModel.content,
                LibraryModel.created_at
            )
            .select_from(LibraryModel)
            .join(MessagesModel, LibraryModel.message_id == MessagesModel.message_id)
            .filter(LibraryModel.user_id == user_id)
            .order_by(LibraryModel.created_at.desc())
            .all()
        )
        
        results = []
        for message_id, content, created_at in library_entries:
            results.append({
                "message_id": message_id,
                "content": content,
                "added_at": created_at
            })

        return results
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user's library.{str(e)}"
        )


@library_router.delete("/remove-from-library")
async def remove_from_library(message_id: str, db: Session = Depends(database.get_db)):
    try:
        entry = db.query(LibraryModel).filter(
            LibraryModel.message_id == message_id
        ).first()
        
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found in library."
            )
        
        db.delete(entry)
        db.commit()
        
        return {"detail": "Message removed from library successfully."}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove message from library."
        )