from fastapi import APIRouter, Depends, status
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user, require_supervisor
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserPublicProfile

router = APIRouter()


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    POST /api/v1/auth/login

    Accepts { username, password } and returns a signed JWT with the user's role.
    Returns HTTP 401 on invalid credentials (intentionally vague for security).
    """
    user: User | None = (
        db.query(User)
        .filter(User.username == payload.username, User.is_active == True)
        .first()
    )

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": "Invalid username or password."},
        )

    token_data = {"sub": user.id, "role": user.role, "username": user.username}
    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        username=user.username,
        role=user.role,
        user=user,
    )


@router.get("/me", response_model=UserPublicProfile)
def get_me(current_user: User = Depends(get_current_user)):
    """
    GET /api/v1/auth/me

    Returns the profile of the currently authenticated user.
    Requires a valid Bearer token.
    """
    return current_user


@router.get("/supervisor-only", response_model=UserPublicProfile)
def supervisor_only_access(current_user: User = Depends(require_supervisor)):
    """
    GET /api/v1/auth/supervisor-only

    Protected route requiring SUPERVISOR or ADMIN role.
    Users with wrong role (e.g. dispatcher) receive HTTP 403 Forbidden.
    """
    return current_user
