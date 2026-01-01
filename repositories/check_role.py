from schemas.user_model import UserModel

class RoleRepository:
    @staticmethod
    def check_role(db, user_id):
        user = (
            db.query(UserModel)
            .filter(UserModel.id == user_id)
            .first()
        )
        
        if not user:
            user = (
                db.query(UserModel)
                .filter(UserModel.firebase_uid == user_id)
                .first()
            )
        
        if not user:
            return "user"
        
        return user.role