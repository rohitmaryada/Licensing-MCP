"""
Tool: search_entitlements

Parameterized search across licenses and entitlements.

This is the only read tool that uses elicitation. Here's why:
- All other tools take a specific ID and return a bounded result.
- search_entitlements takes optional filters and could return 1 or 500 results.
- If the result set is large (>50), flooding Claude's context window degrades
  answer quality — Claude works best with focused, relevant data.
- Elicitation lets the server check the result count FIRST, then ask the user
  to narrow the query before returning data. The user stays in control.

The 50-result threshold is a deliberate product decision, not an arbitrary number:
- Small enough that Claude can reason over all results in one context
- Large enough to be genuinely useful for most queries
- Easy to adjust if demos show it's too tight or too loose
"""

from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_search_entitlements
from licensing_mcp.server_instance import mcp

RESULT_LIMIT = 50  # Elicit narrowing if result count exceeds this


@mcp.tool()
async def search_entitlements(
    entity_name: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Partial company or institution name to filter by. "
                "Case-insensitive. E.g. 'acme' matches 'Acme Corp'."
            ),
        ),
    ] = None,
    product_name: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Partial product name to filter by. "
                "E.g. 'simulink' matches licenses that include Simulink."
            ),
        ),
    ] = None,
    license_status: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Filter by license status. "
                "Valid values: 'active', 'expired', 'trial', 'suspended'."
            ),
        ),
    ] = None,
    license_type: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "Filter by license type. "
                "Valid values: 'enterprise', 'academic', 'individual', 'concurrent', 'trial'."
            ),
        ),
    ] = None,
    expiring_within_days: Annotated[
        Optional[int],
        Field(
            default=None,
            description=(
                "Return only licenses expiring within this many days from today. "
                "E.g. 30 = licenses expiring in the next 30 days."
            ),
        ),
    ] = None,
    min_seat_utilization_pct: Annotated[
        Optional[int],
        Field(
            default=None,
            description=(
                "Return only licenses where seat utilization is at or above this percentage. "
                "E.g. 80 = licenses where at least 80%% of seats are occupied."
            ),
        ),
    ] = None,
) -> dict:
    """
    Search across all licenses and entitlements using optional filters.

    Use this when you need to find licenses matching certain criteria, such as:
    - Licenses for a specific company or institution
    - Licenses that include a specific product (e.g. Simulink)
    - Licenses expiring soon (by days until expiry)
    - Licenses at or near seat capacity (by utilization percentage)
    - Any combination of the above

    At least one filter should be provided. If the result set is large,
    this tool will ask you to narrow the query before returning data —
    this produces a better, more focused answer from the AI.

    Returns a list of matching licenses with seat utilization, expiry, and product count.
    For full product details on a specific license, use get_license_products.
    """
    # ── Step 1: Run the query to get result count ─────────────────────────────
    #
    # We run the query BEFORE deciding whether to return or elicit.
    # This is the key pattern: check first, then decide.
    # The data_access layer returns (results, total_count) for exactly this reason.

    session = get_session()
    try:
        results, total_count = query_search_entitlements(
            session,
            entity_name=entity_name,
            product_name=product_name,
            license_status=license_status,
            license_type=license_type,
            expiring_within_days=expiring_within_days,
            min_seat_utilization_pct=min_seat_utilization_pct,
        )
    finally:
        session.close()

    # ── Step 2: No results ────────────────────────────────────────────────────

    if total_count == 0:
        return {
            "result_count": 0,
            "message": "No licenses matched the provided filters.",
            "filters_applied": _summarise_filters(
                entity_name, product_name, license_status,
                license_type, expiring_within_days, min_seat_utilization_pct,
            ),
        }

    # ── Step 3: Elicit if result set is too large ─────────────────────────────
    #
    # Elicitation is an MCP protocol feature that lets the SERVER pause and ask
    # the USER a question mid-tool-execution. The flow is:
    #
    #   tool runs → count=312 → server sends elicitation/create to Claude Desktop
    #   → Claude Desktop shows the user a prompt → user responds
    #   → server receives the answer → server re-runs the query → returns results
    #
    # The elicitation schema defines what kind of response the server expects.
    # Here we offer specific filter options based on which filters were NOT yet used.

    if total_count > RESULT_LIMIT:
        # Build elicitation prompt dynamically based on unused filters
        unused = _unused_filters(
            entity_name, product_name, license_status,
            license_type, expiring_within_days, min_seat_utilization_pct,
        )

        elicitation_schema = _build_elicitation_schema(unused)

        # mcp.get_context() gives access to the MCP request context, which
        # includes the elicit() method for sending an elicitation/create message.
        ctx = mcp.get_context()
        response = await ctx.elicit(
            message=(
                f"Your search returned {total_count} licenses — too many to reason "
                f"over effectively. Please narrow the results using one or more "
                f"additional filters:"
            ),
            schema=elicitation_schema,
        )

        # response.action tells us what happened:
        # "accept"  — user provided values, available in response.data
        # "decline" — user chose not to narrow; return what we have (capped)
        # "cancel"  — user cancelled; return empty

        if response.action == "cancel":
            return {"result_count": 0, "message": "Search cancelled by user."}

        if response.action == "accept" and response.data:
            # Merge user's narrowing choices with original filters and re-run
            narrowed = _merge_elicited(
                response.data,
                entity_name, product_name, license_status,
                license_type, expiring_within_days, min_seat_utilization_pct,
            )
            session = get_session()
            try:
                results, total_count = query_search_entitlements(session, **narrowed)
            finally:
                session.close()

        # "decline" falls through — return original results capped at RESULT_LIMIT
        if total_count > RESULT_LIMIT:
            results = results[:RESULT_LIMIT]
            truncated = True
        else:
            truncated = False
    else:
        truncated = False

    # ── Step 4: Return results ────────────────────────────────────────────────

    return {
        "result_count": total_count,
        "results_returned": len(results),
        "truncated": truncated,
        "filters_applied": _summarise_filters(
            entity_name, product_name, license_status,
            license_type, expiring_within_days, min_seat_utilization_pct,
        ),
        "licenses": results,
    }


# ── Elicitation helpers ───────────────────────────────────────────────────────

def _summarise_filters(entity_name, product_name, license_status,
                        license_type, expiring_within_days, min_seat_utilization_pct) -> dict:
    """Return a dict of only the filters that were actually provided."""
    return {k: v for k, v in {
        "entity_name": entity_name,
        "product_name": product_name,
        "license_status": license_status,
        "license_type": license_type,
        "expiring_within_days": expiring_within_days,
        "min_seat_utilization_pct": min_seat_utilization_pct,
    }.items() if v is not None}


def _unused_filters(entity_name, product_name, license_status,
                     license_type, expiring_within_days, min_seat_utilization_pct) -> list[str]:
    """Return the names of filters that were NOT provided in the original call."""
    all_filters = {
        "entity_name": entity_name,
        "product_name": product_name,
        "license_status": license_status,
        "license_type": license_type,
        "expiring_within_days": expiring_within_days,
        "min_seat_utilization_pct": min_seat_utilization_pct,
    }
    return [k for k, v in all_filters.items() if v is None]


def _build_elicitation_schema(unused_filters: list[str]) -> dict:
    """
    Build a JSON Schema for the elicitation prompt.

    The schema describes what the server is asking for — Claude Desktop
    renders this as a form for the user to fill in.

    We only include filters the user hasn't already provided, so we're
    not asking them to re-enter what they already gave us.
    """
    properties = {}
    descriptions = {
        "entity_name": "Company or institution name (partial match)",
        "product_name": "Product name (e.g. Simulink, MATLAB Compiler)",
        "license_status": "License status: active | expired | trial | suspended",
        "license_type": "License type: enterprise | academic | individual | concurrent | trial",
        "expiring_within_days": "Expiring within N days (e.g. 30, 60, 90)",
        "min_seat_utilization_pct": "Minimum seat utilization % (e.g. 80 for ≥80% full)",
    }
    types = {
        "entity_name": "string",
        "product_name": "string",
        "license_status": "string",
        "license_type": "string",
        "expiring_within_days": "integer",
        "min_seat_utilization_pct": "integer",
    }

    for f in unused_filters:
        properties[f] = {
            "type": types[f],
            "description": descriptions[f],
        }

    return {
        "type": "object",
        "properties": properties,
        # No required fields — user can fill in any subset
    }


def _merge_elicited(elicited_data: dict,
                     entity_name, product_name, license_status,
                     license_type, expiring_within_days, min_seat_utilization_pct) -> dict:
    """
    Merge the user's elicited narrowing choices with the original filter values.
    Original values take priority — elicited values fill in the blanks.
    """
    return {
        "entity_name": entity_name or elicited_data.get("entity_name"),
        "product_name": product_name or elicited_data.get("product_name"),
        "license_status": license_status or elicited_data.get("license_status"),
        "license_type": license_type or elicited_data.get("license_type"),
        "expiring_within_days": expiring_within_days or elicited_data.get("expiring_within_days"),
        "min_seat_utilization_pct": min_seat_utilization_pct or elicited_data.get("min_seat_utilization_pct"),
    }
