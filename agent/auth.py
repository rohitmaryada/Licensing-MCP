"""
Keycloak OIDC authentication — validates JWTs and extracts email.
Authorization (roles, permissions, audit) is handled by the MCP server's own code.
"""
from functools import lru_cache

import httpx
from jose import JWTError, jwt

KEYCLOAK_URL = "http://localhost:8080"
REALM = "licensing-mcp"
CLIENT_ID = "licensing-agent"
ISSUER = f"{KEYCLOAK_URL}/realms/{REALM}"
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"


@lru_cache(maxsize=1)
def get_jwks() -> dict:
    response = httpx.get(JWKS_URL)
    response.raise_for_status()
    return response.json()


def validate_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            get_jwks(),
            algorithms=["RS256"],
            issuer=ISSUER,
            options={"verify_aud": False},
        )
        return claims
    except JWTError as e:
        raise ValueError(f"Token validation failed: {e}")


def get_actor_email(token: str) -> str:
    """Validate token and return email. This becomes CS_ACTOR_ID for the MCP subprocess."""
    claims = validate_token(token)
    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        raise ValueError("Token missing email claim — check Keycloak client scope mapper")
    return email
