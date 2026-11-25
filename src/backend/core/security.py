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


ADMIN_ROLE = "syxplain-admin"
# Every Syxplain API key starts with this; a token that does not is a Keycloak JWT
API_KEY_PREFIX = "syxp_"
# Keycloak names a client's service-account user "service-account-<client id>"
SERVICE_ACCOUNT_PREFIX = "service-account-"


def grants_server_keys(roles) -> bool:
    """Whether these realm roles allow runs on the server's LLM keys (admin or SERVER_KEYS_ROLE)."""
    return ADMIN_ROLE in roles or get_auth_settings().server_keys_role in roles


class User:
    """
    Represents an authenticated user.

    Attributes:
        user_id: Unique identifier from Keycloak (sub claim)
        email: User's email address (a service account has none: its username stands in)
        roles: Realm roles from Keycloak JWT (realm_access.roles)
    """

    def __init__(self, user_id: str, email: str, roles: list[str] | None = None):
        self.user_id = user_id
        self.email = email
        self.roles = roles or []

    @property
    def is_service_account(self) -> bool:
        """A Keycloak client's service account (technical access, client_credentials grant)."""
        return bool(self.email) and self.email.startswith(SERVICE_ACCOUNT_PREFIX)

    @property
    def is_admin(self) -> bool:
        """Check if user has the syxplain-admin realm role."""
        return ADMIN_ROLE in self.roles

    @property
    def has_server_keys_access(self) -> bool:
        """Check if the user may run on the server's LLM keys."""
        return grants_server_keys(self.roles)

    def __repr__(self) -> str:
        return f"User(id={self.user_id}, email={self.email})"


def check_token_claims(payload: dict, settings: AuthSettings) -> None:
    """
    Accept access tokens only, and only from the allowed Keycloak clients.

    Keycloak signs ID and refresh tokens with the same realm key; they carry
    typ "ID" / "Refresh" and must not authenticate API calls.
    """
    token_type = payload.get("typ")
    if token_type is not None and token_type != "Bearer":
        raise jwt.InvalidTokenError(f"not an access token (typ={token_type})")
    allowed = settings.get_allowed_clients()
    if allowed and payload.get("azp") not in allowed:
        raise jwt.InvalidTokenError(f"client not allowed (azp={payload.get('azp')})")


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
        check_token_claims(payload, settings)
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

        if not email:
            # Service accounts (client_credentials) have no email; their username
            # "service-account-<client>" identifies them wherever an email is recorded
            username = payload.get("preferred_username") or ""
            if username.startswith(SERVICE_ACCOUNT_PREFIX):
                email = username

        roles = payload.get("realm_access", {}).get("roles", [])
        return User(user_id=user_id, email=email, roles=roles)

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


def _authenticate_api_key(raw_key: str) -> User:
    """Authenticate an X-API-Key value; raises HTTPException(401) when it is not valid."""
    try:
        from backend.repositories.api_key_repository import ApiKeyRepository
        from backend.services.api_key_service import ApiKeyService

        db_gen = _get_db_session()()
        db = next(db_gen)
        try:
            return ApiKeyService(ApiKeyRepository(db)).authenticate_by_api_key(raw_key)
        finally:
            with contextlib.suppress(StopIteration):
                next(db_gen)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "ApiKey"},
        )


def authenticate_credentials(
    api_key: str | None, bearer_token: str | None, settings: AuthSettings | None = None
) -> User:
    """
    Authenticate by API key (X-API-Key) or Bearer token. An API key may also come as
    the Bearer token, for clients that can only set an Authorization header.
    Blocking (database or JWKS lookup).

    Raises:
        HTTPException: 401 without valid credentials, 403 for an unverified email
    """
    if not api_key and bearer_token and bearer_token.startswith(API_KEY_PREFIX):
        api_key, bearer_token = bearer_token, None
    if api_key:
        return _authenticate_api_key(api_key)
    if bearer_token:
        return _authenticate_jwt(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer_token),
            settings or get_auth_settings(),
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a Bearer token or X-API-Key header.",
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
    FastAPI dependency that validates either an API key or a JWT (see
    authenticate_credentials; the API key wins when both are sent).

    Returns:
        User object with id, email, and roles

    Raises:
        HTTPException: If authentication fails
    """
    # Warn if both auth methods are provided
    if x_api_key and credentials:
        logger.warning("Request contains both X-API-Key and Bearer token; using API key")

    return authenticate_credentials(
        x_api_key, credentials.credentials if credentials else None, settings
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
