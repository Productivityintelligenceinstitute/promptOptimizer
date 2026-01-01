from pydantic import BaseModel

class AssignPermissionRequest(BaseModel):
    package_name: str
    permission_name: str
    query_limit: int | None = None
    is_enabled: bool = True


class PackagePermissionOut(BaseModel):
    package_name: str
    permission_name: str
    query_limit: int | None
    is_enabled: bool

    class Config:
        from_attributes = True
