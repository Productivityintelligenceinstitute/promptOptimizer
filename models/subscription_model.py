from pydantic import BaseModel

class UpgradeSubscriptionRequest(BaseModel):
    user_id: str
    package_id: str


class CancelSubscriptionRequest(BaseModel):
    user_id: str
