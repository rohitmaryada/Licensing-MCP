"""
MCP server entry point.

Importing a tool module is what registers it with FastMCP — the @mcp.tool()
decorator fires at import time. So this file's job is simply:
  1. Import every tool module (triggering registration)
  2. Run the server

Your colleague adds their top-3 tools by adding three import lines here.
Nothing else in the codebase changes.
"""

# ── Tool registrations ────────────────────────────────────────────────────────
# Bottom 3 (Rohit)
from licensing_mcp.tools import get_license_products        # noqa: F401
from licensing_mcp.tools import get_license_administrators  # noqa: F401
from licensing_mcp.tools import search_entitlements         # noqa: F401

# Top 3 (colleague — uncomment as each tool is merged)
# from licensing_mcp.tools import get_license_status          # noqa: F401
# from licensing_mcp.tools import check_user_entitlements     # noqa: F401
# from licensing_mcp.tools import list_licenses_by_entity     # noqa: F401

# ── Run ───────────────────────────────────────────────────────────────────────
from licensing_mcp.server_instance import mcp


def main():
    """
    Run the MCP server over stdio transport.

    stdio means:
    - Claude Desktop launches this as a subprocess
    - All MCP messages flow over stdin/stdout as JSON-RPC 2.0
    - No network port, no TLS — process isolation is the security boundary
    - In production: swap to streamable-http transport with OAuth 2.1
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
