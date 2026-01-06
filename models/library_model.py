from pydantic import BaseModel

class AddToLibraryRequest(BaseModel):
    user_id: str
    message_id: str