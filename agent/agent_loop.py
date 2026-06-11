"""
The hand-rolled agent loop — what Claude Desktop does internally.

One turn of conversation may take several round-trips to the Claude API:

    ┌────────────────────────────────────────────────────────────┐
    │ 1. send conversation + tool definitions to Claude          │
    │ 2. Claude replies with either:                             │
    │      text (stop_reason == "end_turn")      → done          │
    │      tool_use blocks (stop_reason == "tool_use") → step 3  │
    │ 3. execute each tool call via the MCP bridge               │
    │ 4. append assistant content + tool_result blocks           │
    │ 5. goto 1                                                  │
    └────────────────────────────────────────────────────────────┘

Design notes (the things that bite people):
- Append response.content VERBATIM as the assistant turn. The tool_use
  blocks must stay in history or the API rejects the matching tool_result.
- Every tool_result carries the tool_use_id of the call it answers.
- The API is stateless: the full message list goes up on every request.
- Prompt caching: top-level cache_control auto-caches the conversation
  prefix (tools + system + history), so each loop iteration re-reads the
  prior context at ~10% of input cost instead of full price.
"""

import anthropic

from agent.mcp_bridge import MCPBridge

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000
MAX_LOOPS = 15  # circuit breaker — an agent should never need this many

SYSTEM_PROMPT = (
    "You are the Licensing Intelligence assistant for MathWorks Customer "
    "Service representatives. You help reps diagnose and resolve customer "
    "licensing issues using the available tools.\n"
    "\n"
    "Guidelines:\n"
    "- Diagnose before acting: check entitlements and license status before "
    "proposing any write action.\n"
    "- Write tools (revoke_activation, add_user_to_license, etc.) require a "
    "'reason' — write a complete business justification including what you "
    "observed, since it becomes the permanent audit record.\n"
    "- revoke_activation returns confirmation_required on first call: relay "
    "the proposed action and evidence to the rep, and only call again with "
    "confirm=true after the rep explicitly agrees.\n"
    "- After any write action, offer to show the audit trail.\n"
    "- Be concise. Lead with the answer, then the supporting detail."
)


async def run_agent_turn(
    client: anthropic.AsyncAnthropic,
    bridge: MCPBridge,
    messages: list,
) -> tuple[str, list[dict]]:
    """
    Run one user turn to completion (including any tool-call round-trips).

    `messages` is mutated in place: the caller owns conversation history
    and must have already appended the new user message.

    Returns (final_text, tool_trace) — the trace lists every tool call made
    this turn so the UI can render what the agent did.
    """
    tool_trace: list[dict] = []

    for _ in range(MAX_LOOPS):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=bridge.claude_tools,
            messages=messages,
            thinking={"type": "adaptive"},
            cache_control={"type": "ephemeral"},  # cache the growing prefix
        )

        # The assistant turn goes into history verbatim — including any
        # tool_use blocks. Dropping them breaks the tool_use_id pairing.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                b.text for b in response.content if b.type == "text"
            )
            return final_text, tool_trace

        # Execute every tool call in this response, then send all results
        # back together in one user message.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result_text = await bridge.call_tool(block.name, block.input)
                is_error = False
            except Exception as e:
                result_text = f"Tool execution failed: {e}"
                is_error = True

            tool_trace.append({
                "tool": block.name,
                "input": block.input,
                "result_preview": result_text[:300],
                "is_error": is_error,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})

    return (
        "I hit the maximum number of tool-call rounds for one turn. "
        "Please rephrase or break the request into smaller steps.",
        tool_trace,
    )
