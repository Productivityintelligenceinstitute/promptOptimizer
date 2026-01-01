from repositories.user_repository import UserRepository
from repositories.update_role_repository import UpdateRoleRepository

def update_user_role_service(email, new_role, db):
    user = UserRepository.get_user_by_email(email, db)
    if not user:
        return {"status": "User not found."}
    
    if user.role == new_role:
        return {"status": "User already has the specified role."}
    
    UpdateRoleRepository.update_role(user, new_role, db)
        
    return {"status": "User role updated successfully."}