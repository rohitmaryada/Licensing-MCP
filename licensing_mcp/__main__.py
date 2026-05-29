"""
Enables: python -m licensing_mcp

This is cleaner than python licensing_mcp/server.py because:
- It works from any working directory
- It's the standard Python package invocation pattern
- Claude Desktop config uses this form: "args": ["-m", "licensing_mcp"]
"""

from licensing_mcp.server import main

main()
