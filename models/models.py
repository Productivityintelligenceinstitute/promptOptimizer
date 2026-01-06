from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import Text

class Prompt(BaseModel):
    user_id: str
    user_prompt: str
    chat_id: Optional[str] = None

class MessageOut(BaseModel):
    # Expose the database primary key as `id` in responses
    id: Optional[UUID] = None
    role: str
    content: Text

    model_config = ConfigDict(from_attributes=True)

class JetRagRequest(BaseModel):
    query: str
    mode: Optional[str] = "Structured"  # Quick | Structured | Mastery
    top_k: int = 8


class JetContext(BaseModel):
    id: str
    score: float
    text_preview: str
    metadata: Dict[str, Any]


class JetRagResponse(BaseModel):
    answer: str
    contexts: List[JetContext]
