"""Tool: add_user_to_license (CS-L1)"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_add_user_to_license
from licensing_mcp.server_instance import mcp


@mcp.tool()
def add_user_to_license(
    license_id: Annotated[str, Field(description="License to add the user to. Format: L-XXXXX.")],
    user_email: Annotated[str, Field(description="Email of an existing user to add.")],
    reason: Annotated[str, Field(description=(
        "Business justification — who requested this and why. Becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L1+] Add an existing user to a license's user list, granting them
    entitlements to every product on the license.

    Fails with a clear message if the license is at seat capacity — in that
    case look for stale activations (check_user_entitlements) or increase
    the seat count (update_seat_count, CS-L2).

    Requires a CS actor identity. Writes an audit record in all cases.
    """
    return execute_cs_write(
        tool_name="add_user_to_license",
        reason=reason,
        mutate=lambda s: apply_add_user_to_license(s, license_id, user_email),
        target_license_id=license_id,
        target_user_email=user_email,
        args={"license_id": license_id, "user_email": user_email},
    )
