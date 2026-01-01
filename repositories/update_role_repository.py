
class UpdateRoleRepository:
    @staticmethod
    def update_role(user, new_role, db):
        user.role = new_role
        db.commit()
        db.refresh(user)