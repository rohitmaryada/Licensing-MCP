"""Tool: reset_installation_slot (CS-L2)"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_reset_installation_slot
from licensing_mcp.server_instance import mcp


@mcp.tool()
def reset_installation_slot(
    user_email: Annotated[str, Field(description="Email of the user whose installation to clear.")],
    product_name: Annotated[str, Field(description="Product name, e.g. 'MATLAB'.")],
    machine_id: Annotated[str, Field(description="Machine ID of the installation record to clear.")],
    reason: Annotated[str, Field(description=(
        "Business justification (e.g. hardware failure, machine replaced). Becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L2+] Clear an installation record so the user can reinstall the
    product on a replacement machine.

    Use when a machine was lost, failed, or replaced and the old installation
    record blocks a reinstall. This clears the record only — it does not
    revoke activations (use revoke_activation for that).

    Requires a CS-L2 or higher actor. Writes an audit record in all cases.
    """
    return execute_cs_write(
        tool_name="reset_installation_slot",
        reason=reason,
        mutate=lambda s: apply_reset_installation_slot(s, user_email, product_name, machine_id),
        target_user_email=user_email,
        target_product_name=product_name,
        args={"user_email": user_email, "product_name": product_name,
              "machine_id": machine_id},
    )
