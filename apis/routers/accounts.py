from fastapi import APIRouter, HTTPException, status, Depends
import utils.utils as utils
from validator import validator
from database import database
from sqlalchemy.orm import Session
from uuid import uuid4
from models.user_model import UserModel

accounts_router = APIRouter()

@accounts_router.post("/create-account")
async def create_account(account: validator.CreateAccount, db: Session = Depends(database.get_db)):
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
        
        return {"detail": "Account created successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create account."
        )

@accounts_router.post("/login-account")
async def login_account(account: validator.LoginAccount, db: Session = Depends(database.get_db)):
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
