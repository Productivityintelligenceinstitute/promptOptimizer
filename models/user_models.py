from pydantic import BaseModel, Field
from typing import Optional


class CreateAccount(BaseModel):
    full_name: Optional[str] = None


class LoginAccount(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    """Response model for user data"""
    user_id: str = Field(..., description="Unique user identifier from backend")
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User's full name")
    role: str = Field(..., description="User role (e.g., 'user', 'admin')")
    firebase_uid: str = Field(..., description="Firebase authentication UID")
    created_at: Optional[str] = Field(None, description="Account creation timestamp in ISO format")
    package_name: Optional[str] = Field(None, description="Active subscription package name")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "full_name": "John Doe",
                "role": "user",
                "firebase_uid": "firebase-uid-123",
                "created_at": "2024-01-01T00:00:00Z",
                "package_name": "free"
            }
        }