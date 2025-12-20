"""
Security utilities for authentication and authorization.

Provides JWT validation for Supabase tokens and user extraction.
Refactored from the original auth.py for cleaner separation of concerns.
"""
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import get_auth_settings, AuthSettings
from backend.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

# Security scheme for bearer token authentication
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


class User:
    """
    Represents an authenticated user.

    Attributes:
        user_id: Unique identifier from Supabase
        email: User's email address
    """
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email

    def __repr__(self) -> str:
        return f"User(id={self.user_id}, email={self.email})"


def decode_jwt_token(
    token: str,
    settings: AuthSettings
) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string
        settings: Auth settings with JWT secret

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    if not settings.supabase_jwt_secret:
        raise AuthenticationError(
            message="Authentication not configured",
            reason="JWT secret not set"
        )

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError(
            message="Token has expired",
            reason="expired"
        )
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(
            message="Invalid authentication credentials",
            reason=str(e)
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: AuthSettings = Depends(get_auth_settings)
) -> User:
    """
    FastAPI dependency that validates JWT token and returns the current user.

    Args:
        credentials: Bearer token from request header
        settings: Injected auth settings

    Returns:
        User object with id and email

    Raises:
        HTTPException: If authentication fails
    """
    try:
        payload = decode_jwt_token(credentials.credentials, settings)

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise AuthenticationError(
                message="Invalid authentication credentials",
                reason="Missing user ID in token"
            )

        return User(user_id=user_id, email=email)

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    settings: AuthSettings = Depends(get_auth_settings)
) -> Optional[User]:
    """
    Optional authentication dependency.

    Returns None if no token provided, otherwise validates and returns user.
    Useful for endpoints that work with or without authentication.

    Args:
        credentials: Optional bearer token
        settings: Injected auth settings

    Returns:
        User object if authenticated, None otherwise
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, settings)
    except HTTPException:
        return None


def verify_user_owns_resource(
    user: User,
    resource_user_id: str,
    resource_type: str = "resource"
) -> None:
    """
    Verify that the current user owns the specified resource.

    Args:
        user: Current authenticated user
        resource_user_id: User ID that owns the resource
        resource_type: Type of resource for error message

    Raises:
        HTTPException: If user doesn't own the resource
    """
    if str(user.user_id) != str(resource_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_type} not found"
        )
