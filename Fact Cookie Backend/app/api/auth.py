"""Authentication and API key routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_login_rate_limit, require_register_rate_limit
from app.api.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
    UserUpdate,
)
from app.core.errors import NotFoundError
from app.db.models import User
from app.db.session import get_db
from app.services import api_key_service, auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
api_keys_router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    await require_register_rate_limit(request)
    user = await auth_service.register_user(db, body.email, body.password, body.name)
    access, refresh, expires = await auth_service.issue_tokens(db, user, request.headers.get("user-agent"))
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires)


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    await require_login_rate_limit(request)
    user = await auth_service.authenticate_user(db, body.email, body.password)
    access, refresh, expires = await auth_service.issue_tokens(db, user, request.headers.get("user-agent"))
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    access, refresh_token, expires = await auth_service.refresh_tokens(db, body.refresh_token, request.headers.get("user-agent"))
    return TokenPair(access_token=access, refresh_token=refresh_token, expires_in=expires)


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    await auth_service.revoke_refresh_token(db, body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        existing = await auth_service.get_user_by_email(db, body.email)
        if existing and existing.id != user.id:
            from app.core.errors import ConflictError

            raise ConflictError("An account with this email already exists.", code="email_taken")
        user.email = body.email.lower()
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(body: PasswordResetRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    token = await auth_service.request_password_reset(db, body.email)
    # Email sending is a logged stub; in production wire an email provider here.
    if token:
        from app.core.logging import get_logger

        get_logger(__name__).info("password_reset_token_issued", extra={"extra_fields": {"email": body.email}})
    return {"status": "accepted"}


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(body: PasswordResetConfirm, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    await auth_service.confirm_password_reset(db, body.token, body.password)


@api_keys_router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreated:
    api_key, full_key = await api_key_service.create_api_key(db, str(user.id), body.name)
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        key=full_key,
        created_at=api_key.created_at,
    )


@api_keys_router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyOut]:
    keys = await api_key_service.list_api_keys(db, str(user.id))
    return [ApiKeyOut.model_validate(k) for k in keys]


@api_keys_router.delete("/{key_id}", response_model=ApiKeyOut)
async def delete_api_key(
    key_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyOut:
    api_key = await api_key_service.revoke_api_key(db, str(user.id), key_id)
    return ApiKeyOut.model_validate(api_key)
