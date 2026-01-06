from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import database
from schemas.user_model import UserModel
from repositories.check_role import RoleRepository

users_admin_router = APIRouter()


@users_admin_router.get("/admin/users")
async def list_users(
    user_id: str = Query(..., description="Current admin user id"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    q: str | None = Query(None, description="Search by email or full name"),
    db: Session = Depends(database.get_db),
):
    # Ensure requester is admin
    role = RoleRepository.check_role(db, user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can list users")

    query = db.query(UserModel)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (UserModel.email.ilike(like)) | (UserModel.full_name.ilike(like))
        )

    total = query.count()
    users = (
        query.order_by(UserModel.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = [
        {
            "user_id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "firebase_uid": u.firebase_uid,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]

    pages = (total + size - 1) // size if size else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


