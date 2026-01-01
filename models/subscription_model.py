from pydantic import BaseModel, Field
from uuid import UUID

class UpgradeSubscriptionRequest(BaseModel):
    user_id: UUID = Field(..., description="Unique identifier for the user")
    package_id: UUID = Field(..., description="Unique identifier for the package")


class CancelSubscriptionRequest(BaseModel):
    user_id: UUID = Field(..., description="Unique identifier for the user")
