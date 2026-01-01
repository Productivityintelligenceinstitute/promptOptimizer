from pydantic import BaseModel, Field
from uuid import UUID

class RemoveChat(BaseModel):
    user_id: UUID = Field(..., description="Message ID")
    chat_id: UUID = Field(..., description="Message ID")