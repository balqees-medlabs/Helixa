"""Auth HTTP shell (contracts/auth-contract.md): login, refresh, logout, me."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx
from app.core.security import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.schemas.auth import LoginRequest, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: auth_service.AuthenticatedUser) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=list(user.roles),
    )


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    conn: Annotated[Connection, Depends(get_tx)],
) -> UserOut:
    try:
        session = auth_service.login(conn, body.email, body.password)
    except auth_service.InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    set_auth_cookies(response, session.access_token, session.refresh_token)
    return _user_out(session.user)


@router.post("/refresh", response_model=UserOut)
def refresh(
    request: Request,
    response: Response,
    conn: Annotated[Connection, Depends(get_tx)],
) -> UserOut | JSONResponse:
    try:
        session = auth_service.rotate(conn, request.cookies.get(REFRESH_COOKIE))
    except (auth_service.InvalidRefresh, auth_service.RefreshReuse):
        # Return (not raise) so the transaction commits: a detected reuse must
        # persist the family revocation even though the request gets a 401.
        failure = JSONResponse(status_code=401, content={"detail": "Invalid session"})
        clear_auth_cookies(failure)
        return failure

    set_auth_cookies(response, session.access_token, session.refresh_token)
    return _user_out(session.user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    conn: Annotated[Connection, Depends(get_tx)],
) -> None:
    auth_service.logout(conn, request.cookies.get(REFRESH_COOKIE))
    clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[AuthContext, Depends(current_user)]) -> UserOut:
    return UserOut(
        id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=list(user.roles),
    )
