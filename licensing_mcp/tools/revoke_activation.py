"""
Tool: revoke_activation (CS-L1)

The Story 2 demo centerpiece. Includes a server-driven elicitation
confirmation: before mutating, the server shows the rep exactly what will
be revoked (machine, heartbeat age, seat impact) and waits for explicit
confirmation. This complements — not replaces — the client-side tool
approval: the server can include computed context the client doesn't have.
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.cs_executor import execute_cs_write
from licensing_mcp.data_access.write_queries import apply_revoke_activation, find_activation
from licensing_mcp.database import get_session
from licensing_mcp.elicitation import ElicitationBase
from licensing_mcp.server_instance import mcp


class ConfirmRevocation(ElicitationBase):
    confirm: bool = Field(
        default=False,
        description="Set to true to confirm revoking this activation.",
    )


@mcp.tool()
async def revoke_activation(
    user_email: Annotated[str, Field(description="Email of the user whose activation to revoke.")],
    product_name: Annotated[str, Field(description="Product name, e.g. 'Simulink'.")],
    machine_id: Annotated[str, Field(description="Machine ID of the activation, e.g. 'MAC-OLD-7291'.")],
    reason: Annotated[str, Field(description=(
        "Business justification for this revocation. Include what you observed "
        "and why revocation is appropriate — this becomes the audit record."
    ))],
) -> dict:
    """
    [CS-L1+] Revoke a product activation on a specific machine, freeing the
    activation slot so the user can activate on a different machine.

    Typical use: a user cannot activate on a new laptop because a stale
    activation on a decommissioned machine still occupies their slot.
    Find the stale activation with check_user_entitlements first.

    The server will ask for confirmation before executing, showing the
    activation's last-heartbeat age and seat impact.

    Requires a CS actor identity. Writes an audit record in all cases.
    """
    # Read-only lookup first so the confirmation shows real data.
    session = get_session()
    try:
        details = find_activation(session, user_email, product_name, machine_id)
    except ValueError as e:
        return {"error": str(e)}
    finally:
        session.close()

    ctx = mcp.get_context()
    response = await ctx.elicit(
        message=(
            f"Confirm revocation: {details['product_name']} activation for "
            f"{details['user_email']} on {details['machine_id']} "
            f"(license {details['license_id']}, status {details['activation_status']}, "
            f"last heartbeat {details['days_since_heartbeat']} days ago). "
            f"The user can re-activate on another machine afterwards."
        ),
        schema=ConfirmRevocation,
    )

    if response.action != "accept" or not response.data or not response.data.confirm:
        return {
            "cancelled": True,
            "message": "Revocation not confirmed — no changes were made.",
        }

    return execute_cs_write(
        tool_name="revoke_activation",
        reason=reason,
        mutate=lambda s: apply_revoke_activation(s, user_email, product_name, machine_id),
        target_license_id=details["license_id"],
        target_user_email=user_email,
        target_product_name=details["product_name"],
        args={"user_email": user_email, "product_name": product_name,
              "machine_id": machine_id},
    )
