from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.authentication.dependency_injection.container import get_service
from app.authentication.schemas import (
    CredentialsRequest,
    IntrospectionResponse,
    LogoutResponse,
    RegistrationResponse,
    SessionResponse,
    UserResponse,
)
from app.core.domain import Context

router = APIRouter(prefix="/authentication", tags=["Authentication"])
Service = Annotated[object, Depends(get_service)]
Auth = Annotated[str, Header(alias="Auth", min_length=32, max_length=256)]


@router.post(
    "/register", response_model=RegistrationResponse, operation_id="authentication_register"
)
async def register(payload: CredentialsRequest, request: Request, service: Service):
    user = await service.register(
        payload.email, payload.password, Context(request.state.request_id)
    )
    return RegistrationResponse(user=UserResponse(external_id=user.external_id, email=user.email))


@router.post("/login", response_model=SessionResponse, operation_id="authentication_login")
async def login(payload: CredentialsRequest, request: Request, service: Service):
    token, session = await service.login(
        payload.email, payload.password, Context(request.state.request_id)
    )
    return SessionResponse(
        token=token, expires_at=session.expires_at, idle_timeout_seconds=service.idle
    )


@router.post("/logout", response_model=LogoutResponse, operation_id="authentication_logout")
async def logout(auth: Auth, request: Request, service: Service):
    await service.logout(auth, Context(request.state.request_id))
    return LogoutResponse()


@router.get(
    "/introspect", response_model=IntrospectionResponse, operation_id="authentication_introspect"
)
async def introspect(auth: Auth, request: Request, service: Service):
    session, actor, idle = await service.introspect(auth, Context(request.state.request_id))
    return IntrospectionResponse(
        user=UserResponse(external_id=actor.external_id, email=actor.email),
        created_at=session.created_at,
        expires_at=session.expires_at,
        idle_expires_at=idle,
    )
