from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LoginRequest(BaseModel):
    username: Username
    password: str = Field(min_length=1)


class SessionResponse(BaseModel):
    authenticated: bool
    username: str
    ai_id: str


class CredentialUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1)
    username: Username
    password: str = Field(min_length=1)


class MessageResponse(BaseModel):
    message: str
