"""
Tool: get_license_products

Returns the complete product catalog assigned to a license.

No elicitation needed here — the input is a specific license ID and the result
is always a single, bounded response. Elicitation is reserved for open-ended
queries where result size is unknown (see search_entitlements.py).
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_license_products

# This `mcp` instance is imported by server.py, which is the single source of
# truth for the FastMCP application. All tools must import the same instance.
from licensing_mcp.server_instance import mcp


@mcp.tool()
def get_license_products(
    license_id: Annotated[
        str,
        Field(
            description=(
                "The license ID to look up. Format: L-XXXXX (e.g. L-99001). "
                "Obtain this from list_licenses_by_entity if you only know the company name."
            )
        ),
    ],
) -> dict:
    """
    Returns the complete product catalog assigned to a specific license —
    including all MATLAB toolboxes and core products (MATLAB, Simulink, etc.).
    Also returns seat utilization, license status, and days until expiry.

    Use this when you have a license ID and need to know:
    - What software products are covered by the license
    - How many seats are in use vs. available
    - When the license expires

    Do NOT use this to look up what a specific user can run — use
    check_user_entitlements for that instead.
    """
    session = get_session()
    try:
        return query_license_products(license_id, session)
    except ValueError as e:
        # License not found — return a structured error Claude can narrate naturally.
        # Never raise an exception to Claude: it produces an unhelpful error message.
        return {"error": str(e), "license_id": license_id}
    except Exception:
        # Catch-all: log internally (in production) but never expose internals.
        return {
            "error": "An unexpected error occurred retrieving license products.",
            "license_id": license_id,
        }
    finally:
        session.close()
