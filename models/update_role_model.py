from pydantic import BaseModel

class UpdateRoleRequestModel(BaseModel):
    email: str
    new_role: str