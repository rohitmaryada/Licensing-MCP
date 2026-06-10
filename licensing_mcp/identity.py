"""
CS actor identity resolution and permission checks.

POC identity model
------------------
The actor is identified by the CS_ACTOR_ID environment variable (set in
claude_desktop_config.json). We resolve it against the cs_users table and
look up the actor's role per call.

Production equivalent
---------------------
CS_ACTOR_ID is replaced by the validated `sub` claim of a PingID-issued JWT,
and the role comes from the token's group claims — the caller can never
self-assert either. The two functions below keep the same signatures; only
their bodies change. See security-considerations-mcp-access.md §2.

Design choices that match production semantics:
- Identity is resolved PER CALL, never cached in module state. Tokens expire
  and roles change; a cached identity would outlive its validity.
- Permissions live in the cs_permissions TABLE, not in code. Adding a tool
  to a role is a data change (like an IdP group edit), not a deploy.
"""

import os

from sqlalchemy.orm import Session

from licensing_mcp.models import CSPermission, CSRole, CSRoleMember, CSUser


class IdentityError(Exception):
    """Raised when the CS actor cannot be resolved. Tool layer converts to a structured error."""


def resolve_actor(session: Session) -> dict:
    """
    Resolve the calling CS actor from CS_ACTOR_ID.

    Returns {id, email, name, role, level} or raises IdentityError.
    """
    actor_email = os.environ.get("CS_ACTOR_ID")
    if not actor_email:
        raise IdentityError(
            "No CS actor identity configured. Write tools require CS_ACTOR_ID "
            "(set in the MCP server's env block in claude_desktop_config.json)."
        )

    user = session.query(CSUser).filter(CSUser.email == actor_email).first()
    if not user:
        raise IdentityError(
            f"CS actor '{actor_email}' is not a registered CS user. "
            f"Write access denied."
        )

    # Highest role wins if an actor somehow holds several.
    role = (
        session.query(CSRole)
        .join(CSRoleMember, CSRole.id == CSRoleMember.cs_role_id)
        .filter(CSRoleMember.cs_user_id == user.id)
        .order_by(CSRole.level.desc())
        .first()
    )
    if not role:
        raise IdentityError(
            f"CS actor '{actor_email}' has no role assignment. Write access denied."
        )

    return {
        "id": user.id,
        "email": user.email,
        "name": f"{user.first_name} {user.last_name}",
        "role": role.name,
        "level": role.level,
    }


def has_permission(session: Session, actor: dict, tool_name: str) -> bool:
    """True if the actor's role is granted tool_name in cs_permissions."""
    role = session.query(CSRole).filter(CSRole.name == actor["role"]).first()
    if not role:
        return False
    grant = (
        session.query(CSPermission)
        .filter(
            CSPermission.role_id == role.id,
            CSPermission.tool_name == tool_name,
        )
        .first()
    )
    return grant is not None


def minimum_role_for(session: Session, tool_name: str) -> str | None:
    """
    The lowest role level granted tool_name — used in rejection messages so
    the agent can tell the rep exactly what escalation is needed.
    """
    role = (
        session.query(CSRole)
        .join(CSPermission, CSRole.id == CSPermission.role_id)
        .filter(CSPermission.tool_name == tool_name)
        .order_by(CSRole.level.asc())
        .first()
    )
    return role.name if role else None
