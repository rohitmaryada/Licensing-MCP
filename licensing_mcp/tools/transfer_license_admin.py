"""Tool: transfer_license_admin (CS-L3)"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_transfer_license_admin
from licensing_mcp.server_instance import mcp


@mcp.tool()
def transfer_license_admin(
    license_id: Annotated[str, Field(description="License whose administration to transfer. Format: L-XXXXX.")],
    from_email: Annotated[str, Field(description="Email of the current administrator.")],
    to_email: Annotated[str, Field(description="Email of the new administrator — must be an active user on the license.")],
    reason: Annotated[str, Field(description=(
        "Business justification — e.g. previous admin left the company, IT contact change. "
        "Becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L3 only] Transfer license administration from one user to another.
    The new administrator must already be an active user on the license
    (use add_user_to_license first if not).

    This is a contract-level change — only CS-L3 (account management) may
    perform it. Lower-tier actors will be rejected and the attempt logged.

    Writes an audit record in all cases.
    """
    return execute_cs_write(
        tool_name="transfer_license_admin",
        reason=reason,
        mutate=lambda s: apply_transfer_license_admin(s, license_id, from_email, to_email),
        target_license_id=license_id,
        target_user_email=to_email,
        args={"license_id": license_id, "from_email": from_email, "to_email": to_email},
    )
