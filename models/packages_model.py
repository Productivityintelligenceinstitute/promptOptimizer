from pydantic import BaseModel

class CreatePackageRequest(BaseModel):
    package_name: str
    is_custom: bool = False


class PackageOut(BaseModel):
    package_id: str
    package_name: str
    is_custom: bool

    class Config:
        from_attributes = True

class AssignPackage(BaseModel):
    user_email: str
    package_name: str
