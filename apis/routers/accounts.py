from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from uuid import uuid4
from typing import Optional
import logging

from models import user_models
from database import database
from dependencies.auth import verify_firebase_token
from schemas.user_model import UserModel
from schemas.subscription_model import SubscriptionsModel

logger = logging.getLogger(__name__)
accounts_router = APIRouter()

@accounts_router.post(
    "/create-account",
    status_code=status.HTTP_201_CREATED,
    summary="Create or update user account",
    description="Creates a new user account or updates existing account if it already exists (idempotent)",
    responses={
        201: {"description": "Account created successfully"},
        200: {"description": "Account already exists"},
        400: {"description": "Invalid request data"},
        500: {"description": "Internal server error"},
    },
)
async def create_account(
    request: user_models.CreateAccount,
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
) -> dict:
    """
    Create or update user account.
    
    This endpoint is idempotent - it will create a new account if the user
    doesn't exist, or update the existing account if it does. Safe to call
    multiple times.
    """
    try:
        firebase_uid: Optional[str] = decoded_token.get("uid")
        email: Optional[str] = decoded_token.get("email")

        if not firebase_uid:
            logger.warning("Firebase UID not found in decoded token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token: UID not found"
            )

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not available from Firebase token",
            )

        # Extract full_name (normalize empty string to None)
        full_name: Optional[str] = None
        if request.full_name:
            stripped_name = request.full_name.strip()
            full_name = stripped_name if stripped_name else None

        # Check if user already exists
        existing_user: Optional[UserModel] = (
            db.query(UserModel)
            .filter(UserModel.firebase_uid == firebase_uid)
            .first()
        )

        if existing_user:
            # Update full_name if provided and different
            updated = False
            if full_name and existing_user.full_name != full_name:
                existing_user.full_name = full_name
                updated = True
            
            if updated:
                try:
                    db.commit()
                    db.refresh(existing_user)
                    logger.info(f"Updated user account for firebase_uid: {firebase_uid}")
                except SQLAlchemyError as e:
                    logger.error(f"Database error while updating user: {e}", exc_info=True)
                    db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update account"
                    )
            
            return {"detail": "Account already exists"}

        # Create new user
        try:
            new_user = UserModel(
                user_id=str(uuid4()),
                firebase_uid=firebase_uid,
                full_name=full_name,
                email=email,
                role="user",  # Explicit default role
            )
            db.add(new_user)
            db.flush()  # Flush to get user_id before creating subscription

            # Create default subscription
            subscription = SubscriptionsModel(
                subscription_id=str(uuid4()),
                user_id=new_user.user_id,
                package_id=1,  # Default free package
                status="active",
                end_date=None,
            )
            db.add(subscription)
            db.commit()
            db.refresh(new_user)

            logger.info(f"Created new user account: {new_user.user_id} for firebase_uid: {firebase_uid}")
            return {"detail": "Account created successfully"}

        except SQLAlchemyError as e:
            logger.error(f"Database error while creating user: {e}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create account due to database error"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error while creating account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating account"
        )

@accounts_router.get(
    "/me",
    response_model=user_models.UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user",
    description="Retrieves the current authenticated user's data based on Firebase token",
    responses={
        200: {
            "description": "User data retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": "123e4567-e89b-12d3-a456-426614174000",
                        "email": "user@example.com",
                        "full_name": "John Doe",
                        "role": "user",
                        "firebase_uid": "firebase-uid-123",
                        "created_at": "2024-01-01T00:00:00Z"
                    }
                }
            }
        },
        404: {"description": "User not found in database"},
        401: {"description": "Invalid or expired authentication token"},
        500: {"description": "Internal server error"},
    },
)
async def get_current_user(
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
) -> user_models.UserResponse:
    """
    Get current authenticated user data.
    
    This endpoint retrieves user information from the database based on the
    Firebase authentication token. The user must exist in the database
    (created via /create-account endpoint).
    """
    try:
        firebase_uid: Optional[str] = decoded_token.get("uid")
        
        if not firebase_uid:
            logger.warning("Firebase UID not found in decoded token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token: UID not found"
            )
        
        # Find user by firebase_uid
        user: Optional[UserModel] = (
            db.query(UserModel)
            .filter(UserModel.firebase_uid == firebase_uid)
            .first()
        )
        
        if not user:
            logger.warning(f"User not found for firebase_uid: {firebase_uid}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please create an account first."
            )
        
        # Validate required fields
        if not user.user_id or not user.email:
            logger.error(f"User {user.user_id} has missing required fields")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User data is incomplete"
            )
        
        # Format created_at timestamp
        created_at_str: Optional[str] = None
        if user.created_at:
            try:
                created_at_str = user.created_at.isoformat()
            except (AttributeError, ValueError) as e:
                logger.warning(f"Failed to format created_at for user {user.user_id}: {e}")
        
        return user_models.UserResponse(
            user_id=user.user_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role or "user",  # Default role if not set
            firebase_uid=user.firebase_uid or firebase_uid,
            created_at=created_at_str,
        )
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching user: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while retrieving user data"
        )
    except Exception as e:
        logger.error(f"Unexpected error while fetching user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving user data"
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
