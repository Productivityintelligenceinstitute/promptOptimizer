from fastapi import APIRouter, HTTPException, status, Depends
import utils.utils as utils
from models import user_models
from database import database
from sqlalchemy.orm import Session
from uuid import uuid4
from schemas.user_model import UserModel
from schemas.subscription_model import SubscriptionsModel

accounts_router = APIRouter()

@accounts_router.post("/create-account")
async def create_account(account: user_models.CreateAccount, db: Session = Depends(database.get_db)):
    try:
        existing_user = db.query(UserModel).filter(UserModel.email == account.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered."
            )
        
        new_user = UserModel(
            user_id=str(uuid4()),
            full_name=account.full_name,
            email=account.email,
            password=utils.get_password_hash(account.password)
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        new_subscription = SubscriptionsModel(
            subscription_id=str(uuid4()),
            user_id=new_user.user_id,
            package_id=1,
            status="active",
            end_date=None
        )
        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)
        
        return {"detail": "Account created successfully."}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create account."
        )

@accounts_router.post("/login-account")
async def login_account(account: user_models.LoginAccount, db: Session = Depends(database.get_db)):
    try:
        user = db.query(UserModel).filter(UserModel.email == account.email).first()
        if not user or not utils.verify_password(account.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )
        
        return {"detail": f"Login successful for, {user.full_name} with user id {user.user_id}."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login."
        )

@accounts_router.delete("/delete-account/{user_id}")
async def delete_account(user_id: str, db: Session = Depends(database.get_db)):
    try:
        user = db.query(UserModel).filter(UserModel.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        db.delete(user)
        db.commit()
        
        return {"detail": "Account deleted successfully."}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account."
        )
