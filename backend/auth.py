from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os
from typing import Optional

security = HTTPBearer()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

class User:
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Validates JWT token from Supabase and extracts user information.
    """
    token = credentials.credentials

    try:
        # Decode JWT token
        # For Supabase, we validate the token using the JWT secret
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated"
        )

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return User(user_id=user_id, email=email)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[User]:
    """
    Optional authentication - returns None if no token provided.
    Useful for endpoints that work with or without authentication.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

async def delete_supabase_user(user_id: str) -> None:
    """
    Deletes a user from Supabase Auth using the Admin API.
    Requires SUPABASE_SERVICE_ROLE_KEY environment variable.
    """
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not service_role_key:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY not set, skipping Supabase user deletion")
        return

    if not SUPABASE_URL:
        logger.warning("SUPABASE_URL not set, skipping Supabase user deletion")
        return

    # Supabase Admin API endpoint for user deletion
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.delete(url, headers=headers)

        if response.status_code == 200 or response.status_code == 204:
            logger.info(f"Successfully deleted Supabase user: {user_id}")
        elif response.status_code == 404:
            logger.warning(f"Supabase user not found (may already be deleted): {user_id}")
        else:
            error_detail = response.text
            logger.error(f"Failed to delete Supabase user {user_id}: {response.status_code} - {error_detail}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete user from authentication provider: {error_detail}"
            )
