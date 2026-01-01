from pydantic import BaseModel

class CreatePermissionRequest(BaseModel):
    permission_name: str


class PermissionOut(BaseModel):
    permission_id: int
    permission_name: str

    class Config:
        from_attributes = True
