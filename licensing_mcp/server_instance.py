"""
Singleton FastMCP application instance.

Why a separate file?
--------------------
All tool files need to import `mcp` to register with @mcp.tool().
server.py needs to import all tools (so they register) AND run mcp.
If mcp lived in server.py, tool files importing from server.py would
create a circular import: server → tools → server.

Solution: mcp lives here. Tools import from here. server.py imports
tools (triggering registration) then calls mcp.run().
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="licensing-mcp",
    instructions=(
        "You have access to MathWorks licensing and entitlement data. "
        "Use the available tools to look up license status, products, "
        "administrators, and entitlements. "
        "Always use a specific license ID when you have one. "
        "Use search_entitlements when you need to find licenses by criteria "
        "such as company name, product, expiry window, or seat utilization."
    ),
)
