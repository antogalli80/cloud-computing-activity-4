from typing import Literal

from pydantic import BaseModel, ConfigDict


class SuccessResponse(BaseModel):
    """Standard response returned by available endpoints."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "status": "success",
                "message": "Endpoint is available.",
            }
        },
    )

    status: Literal["success"] = "success"
    message: str = "Endpoint is available."


class ErrorResponse(BaseModel):
    """Standard error response returned by the API."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "status": "error",
                "code": "not_found",
                "message": "The requested resource was not found.",
            }
        },
    )

    status: Literal["error"] = "error"
    code: str
    message: str
