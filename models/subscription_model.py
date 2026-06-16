from pydantic import BaseModel

class UpgradeSubscriptionRequest(BaseModel):
    user_id: str | None = None
    package_id: str


class CancelSubscriptionRequest(BaseModel):
    user_id: str | None = None
