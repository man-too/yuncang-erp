from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    display_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True
