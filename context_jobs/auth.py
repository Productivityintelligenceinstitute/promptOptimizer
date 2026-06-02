"""Firebase auth helpers for Context Jobs routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from dependencies.auth import verify_firebase_token


def get_authenticated_user_id(
    decoded_token: dict = Depends(verify_firebase_token),
) -> str:
    user_id = decoded_token.get("uid") or decoded_token.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user id not found in token",
        )
    return str(user_id)
