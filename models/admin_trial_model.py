from pydantic import BaseModel, Field


class ExtendTrialRequest(BaseModel):
    user_email: str = Field(..., description="Email of the trial user to extend")
    days: int = Field(..., gt=0, description="Number of days to add to the trial")
