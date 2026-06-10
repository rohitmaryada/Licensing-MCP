"""
MCP prompts — user-invocable conversation starters.

Prompts are the third MCP primitive (tools = model-invoked, resources =
app-attached, prompts = USER-invoked). In Claude Desktop they appear in the
"+" menu under the server's name; the user picks one deliberately, fills in
the arguments, and the rendered text is injected as their message — which
then drives the tool calls.

These two map directly onto the Week 4 demo scripts, so the presenter can
trigger each story from a menu instead of typing the scenario by hand.
"""

from licensing_mcp.server_instance import mcp


@mcp.prompt(title="License health review")
def license_health_review(entity_name: str) -> str:
    """Full health check of every license held by a company or institution."""
    return (
        f"Run a license health review for {entity_name}:\n"
        f"1. Pull all of their licenses and list each with status, seat "
        f"utilization, and expiry date.\n"
        f"2. Flag any license expiring within 60 days.\n"
        f"3. Flag any license at or above 90% seat capacity.\n"
        f"4. Flag any license that looks under-used (below 25% utilization) — "
        f"a renewal-risk signal.\n"
        f"5. Summarise the account's overall licensing health in 2–3 sentences."
    )


@mcp.prompt(title="Diagnose activation issue")
def diagnose_activation_issue(user_email: str, product_name: str) -> str:
    """Diagnose why a user cannot activate a product — the CS Tier-1 workflow."""
    return (
        f"A user reports they cannot activate {product_name}. Diagnose the issue:\n"
        f"1. Check entitlements for {user_email} — are they entitled to "
        f"{product_name}, and on which license?\n"
        f"2. Check that license's status and seat utilization — is it active, "
        f"and are seats available?\n"
        f"3. Look at their existing activations of {product_name} — is a stale "
        f"activation (old heartbeat, inactive status) occupying their slot?\n"
        f"4. Recommend a resolution. If a stale activation should be revoked, "
        f"say which machine and why — but do not revoke until I confirm."
    )
