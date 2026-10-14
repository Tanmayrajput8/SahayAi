"""FastAPI dependency factories for JWT authentication and role-based authorization."""
from typing import List

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole

# Bearer token extractor — does NOT auto-error so we can return custom JSON
_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_user_from_token(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> User:
    """Shared helper: validate Bearer token and return the matching User row."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token", "message": "Authentication token is required."},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise ValueError("No subject claim")
    except JWTError as exc:
        # Distinguish expired vs invalid
        msg = "Token has expired." if "expired" in str(exc).lower() else "Invalid or malformed token."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": msg},
        ) from exc

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user_not_found", "message": "User account not found or inactive."},
        )
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Require any authenticated user (any role)."""
    return _extract_user_from_token(credentials, db)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Return user if a valid Bearer token is provided, or None if unauthenticated."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None



def require_roles(allowed_roles: List[UserRole]):
    """Factory that returns a dependency enforcing one of the given roles."""

    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"Role '{user.role}' is not permitted for this action.",
                },
            )
        return user

    return _check


# Convenience pre-built role guards
require_dispatcher = require_roles([UserRole.DISPATCHER, UserRole.SUPERVISOR, UserRole.ADMIN])
require_supervisor = require_roles([UserRole.SUPERVISOR, UserRole.ADMIN])
require_admin = require_roles([UserRole.ADMIN])
