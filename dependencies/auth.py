from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from firebase_admin import auth
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()

def verify_firebase_token(token=Depends(security)):
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return decoded_token
    except ValueError as e:
        # Firebase Admin SDK not initialized
        logger.error(f"Firebase Admin SDK error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase Admin SDK not initialized",
        )
    except Exception as e:
        # Token verification failed
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )
