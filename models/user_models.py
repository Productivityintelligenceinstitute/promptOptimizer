from pydantic import BaseModel

class CreateAccount(BaseModel):
    full_name: str | None = None

class LoginAccount(BaseModel):
    email: str
    password: str