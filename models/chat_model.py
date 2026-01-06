from pydantic import BaseModel

class RemoveChat(BaseModel):
    user_id: str
    chat_id: str