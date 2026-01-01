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