from typing import Optional
from pydantic import BaseModel

class Prompt(BaseModel):
    user_prompt: str
    chat_id: Optional[str] = None
