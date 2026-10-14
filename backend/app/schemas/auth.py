from pydantic import BaseModel, EmailStr, ConfigDict


class LoginRequest(BaseModel):
    """Credentials submitted to POST /api/v1/auth/login."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Successful JWT response."""
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_id: str
    username: str
    role: str
    user: "UserPublicProfile | None" = None


class UserPublicProfile(BaseModel):
    """Safe public representation of an authenticated user."""
    id: str
    username: str
    full_name: str
    email: str
    role: str
    badge_number: str | None = None

    model_config = ConfigDict(from_attributes=True)
