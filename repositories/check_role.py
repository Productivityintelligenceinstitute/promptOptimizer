from schemas.user_model import UserModel


class RoleRepository:
    @staticmethod
    def check_role(db, user_id):
        """
        Resolve role for a user id or firebase_uid, considering only active (non-deleted) users.
        """
        user = (
            db.query(UserModel)
            .filter(
                UserModel.id == user_id,
                UserModel.is_active.is_(True),
                UserModel.deleted_at.is_(None),
            )
            .first()
        )

        if not user:
            user = (
                db.query(UserModel)
                .filter(
                    UserModel.firebase_uid == user_id,
                    UserModel.is_active.is_(True),
                    UserModel.deleted_at.is_(None),
                )
                .first()
            )

        if not user:
            return "user"

        return user.role