"""
Tool: get_license_status

Returns the health snapshot of a license: status, seat utilization, and expiry.
Single bounded lookup — no elicitation needed.

Use this when the question is "is this license active / at capacity / expiring soon?"
Use get_license_products when the question is "what software does this license cover?"
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_license_status
from licensing_mcp.server_instance import mcp


@mcp.tool()
def get_license_status(
    license_id: Annotated[
        str,
        Field(
            description=(
                "The license ID to look up. Format: L-XXXXX (e.g. L-99001). "
                "Use list_licenses_by_entity first if you only know the company name."
            )
        ),
    ],
) -> dict:
    """
    Returns the current health snapshot of a license: active/expired/suspended status,
    seat utilization (seats used vs. total), and days until expiry.

    Use this when you need to know:
    - Whether a license is currently active
    - How many seats are in use vs. available (at capacity?)
    - When the license expires

    Do NOT use this to see what products are covered — use get_license_products for that.
    Do NOT use this to see what a specific user can run — use check_user_entitlements.
    """
    session = get_session()
    try:
        return query_license_status(license_id, session)
    except ValueError as e:
        return {"error": str(e), "license_id": license_id}
    except Exception:
        return {
            "error": "An unexpected error occurred retrieving license status.",
            "license_id": license_id,
        }
    finally:
        session.close()
