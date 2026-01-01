from pydantic import BaseModel

class CreatePackageRequest(BaseModel):
    package_name: str
    is_custom: bool = False


class PackageOut(BaseModel):
    package_id: int
    package_name: str
    is_custom: bool

    class Config:
        from_attributes = True
