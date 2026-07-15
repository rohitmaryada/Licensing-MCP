"""
Tool: find_user

Resolve a person's NAME (or partial email) to matching user accounts, each with
their company — so a CS rep who only has a name can identify the right person
before looking anything else up.

This is the front door of the CS workflow: the rep often starts with just a name.
Names are ambiguous at scale (hundreds of "Jane Doe"s), so this returns a short
list to disambiguate by company/email — then use that email with
check_user_entitlements.
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.database import get_session
from licensing_mcp.data_access.license_queries import query_find_users
from licensing_mcp.server_instance import mcp


@mcp.tool()
def find_user(
    name: Annotated[
        str,
        Field(
            description=(
                "A person's full or partial name (e.g. 'Jane Doe', 'j. doe') or a "
                "partial email. Use this FIRST when you have a user's name but not "
                "their exact email — it returns matching users with their company "
                "so you can pick the right person, then call check_user_entitlements "
                "with that email."
            )
        ),
    ],
    company: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Optional: the user's company/organization name, to narrow common "
                "names (e.g. name='Jane Doe', company='Acme'). Provide it whenever "
                "the rep knows the customer, to avoid a long list of matches."
            ),
        ),
    ] = None,
) -> dict:
    """
    Search for users by name or email and return the matches with their company.

    Use this when you have a person's name (not their email) and need to find
    their account — the typical starting point for a CS request. If several people
    match, the result lists them (with company) so you can disambiguate; ask the
    rep which one, or narrow by company. Once you have the right email, use
    check_user_entitlements to see their licenses and activations.
    """
    session = get_session()
    try:
        return query_find_users(name, session, company=company)
    except ValueError as e:
        return {"error": str(e), "query": name}
    except Exception:
        return {"error": "An unexpected error occurred searching for users.", "query": name}
    finally:
        session.close()
