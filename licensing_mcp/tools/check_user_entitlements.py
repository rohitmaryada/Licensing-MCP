"""
Tool: check_user_entitlements

Returns all products a user is entitled to run, grouped by license,
with per-product activation state.

No elicitation — result is always bounded to one user's entitlements.

This is the diagnostic starting point for "why can't this user activate?" workflows.
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_check_user_entitlements
from licensing_mcp.server_instance import mcp


@mcp.tool()
def check_user_entitlements(
    user_email: Annotated[
        str,
        Field(
            description=(
                "The email address of the user to look up. "
                "E.g. 'jane.doe@acmecorp.com'. Must be an exact match."
            )
        ),
    ],
) -> dict:
    """
    Returns all products a user is entitled to run, grouped by license, with the
    activation state for each product: active, inactive, or never_activated.

    Each entitlement includes a list of activations — all machines the user has
    activated that product on, with the last heartbeat timestamp and days since
    last heartbeat. A high days_since_heartbeat on an inactive activation signals
    a stale seat that can be safely revoked.

    Use this when you need to know:
    - Whether a user is entitled to a specific product
    - Why a user can't activate (stale/inactive activation occupying a seat)
    - Which machines a user has activated a product on

    Do NOT use this to see all users on a license — use get_license_products for seat counts.
    Do NOT use this to check license health — use get_license_status for that.
    """
    session = get_session()
    try:
        return query_check_user_entitlements(user_email, session)
    except ValueError as e:
        return {"error": str(e), "user_email": user_email}
    except Exception:
        return {
            "error": "An unexpected error occurred retrieving user entitlements.",
            "user_email": user_email,
        }
    finally:
        session.close()
