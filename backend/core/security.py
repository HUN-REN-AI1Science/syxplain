"""
Security utilities for authentication and authorization.

Provides dual authentication: JWT validation for Keycloak tokens (RS256 via JWKS)
and API key authentication via X-API-Key header.
"""

import contextlib
import logging

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from backend.core.config import AuthSettings, get_auth_settings
from backend.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

# Security schemes — auto_error=False so we can check both paths
security = HTTPBearer(auto_error=False)
optional_security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Cached JWKS client (initialized lazily)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client(settings: AuthSettings) -> PyJWKClient:
    """Get or create a cached JWKS client for Keycloak public key retrieval."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


class User:
    """
    Represents an authenticated user.

    Attributes:
        user_id: Unique identifier from Keycloak (sub claim)
        email: User's email address
        roles: Realm roles from Keycloak JWT (realm_access.roles)
    """

    def __init__(self, user_id: str, email: str, roles: list[str] | None = None):
        self.user_id = user_id
        self.email = email
        self.roles = roles or []

    @property
    def is_admin(self) -> bool:
        """Check if user has the syxplain-admin realm role."""
        return "syxplain-admin" in self.roles

    @property
    def has_hunren_access(self) -> bool:
        """Check if user has HUN-REN API key access (admin or hunren-member)."""
        return "syxplain-admin" in self.roles or "hunren-member" in self.roles

    def __repr__(self) -> str:
        return f"User(id={self.user_id}, email={self.email})"


def decode_jwt_token(token: str, settings: AuthSettings) -> dict:
    """
    Decode and validate a Keycloak JWT token using RS256 via JWKS.

    Args:
        token: The JWT token string
        settings: Auth settings with Keycloak JWKS endpoint

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    try:
        jwks_client = _get_jwks_client(settings)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        decode_options = {"verify_aud": False}
        decode_kwargs: dict = {
            "algorithms": ["RS256"],
            "options": decode_options,
        }
        if settings.keycloak_issuer:
            decode_kwargs["issuer"] = settings.keycloak_issuer

        payload = jwt.decode(
            token,
            signing_key.key,
            **decode_kwargs,
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT decode failed: token expired")
        raise AuthenticationError(message="Token has expired", reason="expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT decode failed: InvalidTokenError: {e}")
        raise AuthenticationError(message="Invalid authentication credentials", reason=str(e))
    except Exception as e:
        logger.error(f"JWT decode failed: {type(e).__name__}: {e}")
        raise AuthenticationError(message="Authentication service unavailable", reason=str(e))


def _get_db_session():
    """Lazy import to avoid circular imports."""
    from backend.infrastructure.database.connection import get_db

    return get_db


def _authenticate_jwt(credentials: HTTPAuthorizationCredentials, settings: AuthSettings) -> User:
    """Shared JWT authentication logic for both auth dependencies."""
    try:
        payload = decode_jwt_token(credentials.credentials, settings)

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise AuthenticationError(
                message="Invalid authentication credentials",
                reason="Missing user ID in token",
            )

        if email and not payload.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email address.",
            )

        roles = payload.get("realm_access", {}).get("roles", [])
        return User(user_id=user_id, email=email, roles=roles)

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_jwt_only(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: AuthSettings = Depends(get_auth_settings),
) -> User:
    """
    JWT-only auth for internal endpoints. Rejects API keys.

    Returns:
        User object with id, email, and roles

    Raises:
        HTTPException: If no Bearer token or token is invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required. API key authentication is not supported on this endpoint.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _authenticate_jwt(credentials, settings)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_api_key: str | None = Depends(api_key_header),
    settings: AuthSettings = Depends(get_auth_settings),
) -> User:
    """
    FastAPI dependency that validates either a JWT token or API key.

    Authentication order:
    1. If X-API-Key header present → authenticate via API key
    2. Else if Bearer token present → validate JWT (existing flow)
    3. Else → 401

    Returns:
        User object with id, email, and roles

    Raises:
        HTTPException: If authentication fails
    """
    # Path 1: API key authentication
    if x_api_key:
        try:
            from backend.repositories.api_key_repository import ApiKeyRepository
            from backend.services.api_key_service import ApiKeyService

            db_gen = _get_db_session()()
            db = next(db_gen)
            try:
                repo = ApiKeyRepository(db)
                service = ApiKeyService(repo)
                return service.authenticate_by_api_key(x_api_key)
            finally:
                with contextlib.suppress(StopIteration):
                    next(db_gen)
        except AuthenticationError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message,
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # Path 2: JWT Bearer token authentication
    if credentials:
        return _authenticate_jwt(credentials, settings)

    # Path 3: No credentials provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    settings: AuthSettings = Depends(get_auth_settings),
) -> User | None:
    """
    Optional JWT-only authentication dependency.

    Returns None if no credentials provided, otherwise validates and returns user.
    Useful for endpoints that work with or without authentication.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user_jwt_only(credentials, settings)
    except HTTPException:
        return None


def verify_user_owns_resource(
    user: User, resource_user_id: str, resource_type: str = "resource"
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
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource_type} not found"
        )
