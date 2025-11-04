from pydantic import BaseModel

class Prompt(BaseModel):
    user_prompt: str