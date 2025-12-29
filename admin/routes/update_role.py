from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import database
from schemas.user_model import UserModel

update_role_router = APIRouter()

@update_role_router.put("/update-role")
async def update_user_role(user_id: str, new_role: str, db: Session = Depends(database.get_db)):
    try:
        user = db.query(UserModel).filter(UserModel.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found."
            )
        
        user.role = new_role
        db.commit()
        db.refresh(user)
        
        return {"detail": "User role updated successfully."}
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to update user role."
        )