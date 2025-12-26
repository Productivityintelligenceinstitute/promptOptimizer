from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from firebase_admin import auth

security = HTTPBearer()

def verify_firebase_token(token=Depends(security)):
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return decoded_token
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )
