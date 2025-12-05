from typing import Optional
from pydantic import BaseModel, ConfigDict
from typing import Text

class Prompt(BaseModel):
    user_id: str
    user_prompt: str
    chat_id: Optional[str] = None

class CreateAccount(BaseModel):
    full_name: str
    email: str
    password: str

class LoginAccount(BaseModel):
    email: str
    password: str

class MessageOut(BaseModel):
    role: str
    content: Text

    model_config = ConfigDict(from_attributes=True)