from pydantic import BaseModel, Field
from uuid import UUID

class AddToLibraryRequest(BaseModel):
    user_id: UUID = Field(..., description="User ID")
    message_id: UUID = Field(..., description="Message ID")

class RemoveFromLibraryQuery(BaseModel):
    message_id: UUID = Field(..., description="Message ID")