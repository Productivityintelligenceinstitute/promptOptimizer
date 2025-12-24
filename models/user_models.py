from pydantic import BaseModel

class CreateAccount(BaseModel):
    full_name: str
    email: str
    password: str

class LoginAccount(BaseModel):
    email: str
    password: str