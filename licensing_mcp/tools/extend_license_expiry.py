"""Tool: extend_license_expiry (CS-L3)"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_extend_license_expiry
from licensing_mcp.server_instance import mcp


@mcp.tool()
def extend_license_expiry(
    license_id: Annotated[str, Field(description="License to extend. Format: L-XXXXX.")],
    extension_days: Annotated[int, Field(description="Days to extend the expiry by (1–365).")],
    reason: Annotated[str, Field(description=(
        "Business justification — e.g. renewal PO delayed in procurement. "
        "Becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L3 only] Extend a license's expiration date by a number of days.
    An expired license whose new expiry lands in the future is reactivated.

    This is a contract-level change — only CS-L3 (account management) may
    perform it. Lower-tier actors will be rejected and the attempt logged.

    Writes an audit record in all cases.
    """
    return execute_cs_write(
        tool_name="extend_license_expiry",
        reason=reason,
        mutate=lambda s: apply_extend_license_expiry(s, license_id, extension_days),
        target_license_id=license_id,
        args={"license_id": license_id, "extension_days": extension_days},
    )
