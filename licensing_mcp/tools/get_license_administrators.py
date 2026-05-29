"""
Tool: get_license_administrators

Returns the administrator users who manage a specific license.

No elicitation here — single license lookup, bounded result, no ambiguity.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_license_administrators
from licensing_mcp.server_instance import mcp


@mcp.tool()
def get_license_administrators(
    license_id: Annotated[
        str,
        Field(
            description=(
                "The license ID to look up. Format: L-XXXXX (e.g. L-99001). "
                "Obtain from list_licenses_by_entity if you only know the company name."
            )
        ),
    ],
) -> dict:
    """
    Returns the list of administrator users who manage a specific license.
    License administrators are the designated contacts at a customer organization
    who can manage user access and are the primary escalation point for license issues.

    Use this when you need to know:
    - Who at a company is responsible for managing a license
    - Who to contact about license administration questions
    - How long someone has been an administrator (admin_since date)

    Do NOT use this to list all users on a license — administrators are a small
    subset. For all users, the license seat utilization is in get_license_products.
    """
    session = get_session()
    try:
        return query_license_administrators(license_id, session)
    except ValueError as e:
        return {"error": str(e), "license_id": license_id}
    except Exception:
        return {
            "error": "An unexpected error occurred retrieving license administrators.",
            "license_id": license_id,
        }
    finally:
        session.close()
