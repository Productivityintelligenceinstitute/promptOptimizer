from schemas.user_model import UserModel

class UserRepository:
    @staticmethod
    def get_user_by_email(email, db):
        return (
            db.query(UserModel)
            .filter(
                UserModel.email == email
            )
            .first()
        )

    @staticmethod
    def get_active_by_firebase_uid(firebase_uid: str, db):
        return (
            db.query(UserModel)
            .filter(
                UserModel.firebase_uid == firebase_uid,
                UserModel.is_active.is_(True),
                UserModel.deleted_at.is_(None),
            )
            .first()
        )