"""
Tool: list_licenses_by_entity

Returns all licenses belonging to a company or institution, matched by name.

No elicitation — capped at 20 entities with a truncation message if exceeded.
In practice, entity name searches are specific enough that the cap is never hit.
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_list_licenses_by_entity
from licensing_mcp.server_instance import mcp


@mcp.tool()
def list_licenses_by_entity(
    entity_name: Annotated[
        str,
        Field(
            description=(
                "Partial company or institution name to search for. "
                "Case-insensitive. E.g. 'acme' matches 'Acme Corp', "
                "'mit' matches 'MIT', 'boeing' matches 'Boeing Co'."
            )
        ),
    ],
) -> dict:
    """
    Returns all licenses held by entities whose name matches the search query.
    Results are grouped by entity. Each license includes seat utilization,
    status, expiry, and product count.

    Use this as the entry point when you only know a company or institution name
    and need to find their license IDs before calling other tools.

    Use this when you need to know:
    - What licenses a company or university holds
    - How many licenses an entity has across different license types
    - The license IDs needed to call get_license_status or get_license_products

    Do NOT use this to search across the full dataset by product or status —
    use search_entitlements for that instead.
    """
    session = get_session()
    try:
        return query_list_licenses_by_entity(entity_name, session)
    except ValueError as e:
        return {"error": str(e), "query": entity_name}
    except Exception:
        return {
            "error": "An unexpected error occurred searching for entity licenses.",
            "query": entity_name,
        }
    finally:
        session.close()
