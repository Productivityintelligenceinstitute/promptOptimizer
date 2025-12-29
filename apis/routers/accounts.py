from fastapi import APIRouter, HTTPException, status, Depends
from models import user_models
from database import database
from dependencies.auth import verify_firebase_token
from sqlalchemy.orm import Session
from uuid import uuid4
from schemas.user_model import UserModel
from schemas.subscription_model import SubscriptionsModel

accounts_router = APIRouter()

@accounts_router.post("/create-account")
async def create_account(
    token: str,
    # decoded_token=Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
):
    try:
        
        decoded_token = verify_firebase_token(token)
        
        firebase_uid = decoded_token["uid"]
        email = decoded_token.get("email")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not available from Firebase token",
            )

        user = (
            db.query(UserModel)
            .filter(UserModel.firebase_uid == firebase_uid)
            .first()
        )

        if user:
            return {"detail": "Account already exists"}

        user = UserModel(
            user_id=str(uuid4()),
            firebase_uid=firebase_uid,
            email=email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        subscription = SubscriptionsModel(
            subscription_id=str(uuid4()),
            user_id=user.user_id,
            package_id=1,
            status="active",
            end_date=None,
        )
        db.add(subscription)
        db.commit()

        return {"detail": "Account created successfully"}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create account",
        )

@accounts_router.post("/login-account")
async def login_account(account: user_models.LoginAccount, db: Session = Depends(database.get_db)):
    try:
        user = db.query(UserModel).filter(UserModel.email == account.email).first()
        if not user or not user.email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email."
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
