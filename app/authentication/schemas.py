import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CredentialsRequest(BaseModel):
    """Credentials accepted by registration and login operations."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        min_length=3,
        max_length=254,
        examples=["student@example.com"],
    )
    password: str = Field(
        min_length=12,
        max_length=128,
        examples=["correct-horse-battery-staple"],
        json_schema_extra={"writeOnly": True},
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_and_validate_email(cls, value: object) -> str:
        """Normalize email identity and reject malformed values."""

        if not isinstance(value, str):
            raise ValueError("Email must be a string.")

        email = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Email format is invalid.")
        return email


class UserResponse(BaseModel):
    """Public user information that never includes credentials."""

    model_config = ConfigDict(extra="forbid")

    external_id: int = Field(ge=1, examples=[1])
    email: str = Field(examples=["student@example.com"])


class RegistrationResponse(BaseModel):
    """Response returned after a user is registered."""

    status: Literal["success"] = "success"
    user: UserResponse


class SessionResponse(BaseModel):
    """Opaque session token returned only when login succeeds."""

    status: Literal["success"] = "success"
    token: str = Field(description="Sensitive opaque credential returned once at login.")
    token_type: Literal["opaque"] = "opaque"
    expires_at: datetime
    idle_timeout_seconds: int


class IntrospectionResponse(BaseModel):
    """Public session and user data returned for an active token."""

    status: Literal["success"] = "success"
    active: Literal[True] = True
    user: UserResponse
    created_at: datetime
    expires_at: datetime
    idle_expires_at: datetime


class LogoutResponse(BaseModel):
    """Confirmation that a session has been revoked."""

    status: Literal["success"] = "success"
    message: Literal["Session closed."] = "Session closed."
