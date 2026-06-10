"""Tool: update_seat_count (CS-L2)"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_update_seat_count
from licensing_mcp.server_instance import mcp


@mcp.tool()
def update_seat_count(
    license_id: Annotated[str, Field(description="License to update. Format: L-XXXXX.")],
    new_seat_count: Annotated[int, Field(description="The new total seat count (not a delta).")],
    reason: Annotated[str, Field(description=(
        "Business justification — e.g. purchase order number for an increase, "
        "account team approval for a decrease. Becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L2+] Set a license's total seat count (increase or decrease).

    Decreases are rejected if they would drop below the number of currently
    occupied seats — remove users first in that case.

    Requires a CS-L2 or higher actor. Writes an audit record in all cases.
    """
    return execute_cs_write(
        tool_name="update_seat_count",
        reason=reason,
        mutate=lambda s: apply_update_seat_count(s, license_id, new_seat_count),
        target_license_id=license_id,
        args={"license_id": license_id, "new_seat_count": new_seat_count},
    )
