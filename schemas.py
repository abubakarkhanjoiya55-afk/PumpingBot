from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class MT5Credentials(BaseModel):
    mt5_login: int
    mt5_password: str
    mt5_server: str


class Token(BaseModel):
    access_token: str
    token_type: str