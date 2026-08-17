# Gemini/ADK Secretary Agent - interactive ADK session on Gemini.
# =============================================================================
# The Gemini analogue of agent-grok-secretary. Holds a PERSISTENT conversation:
# receives the CEO's messages over HTTP (POST /turn on :9000) and, per turn,
# runs one ADK Runner turn over a persistent session on Gemini 3.5 Flash,
# streaming each reply back to the panel via the relay. The Secretary's
# CEO-authority tools (read_company_state / read_task / search_tasks /
# submit_directive) are wired as the robofleet-secretary MCP server via an ADK
# McpToolset, which calls /api/secretary/* with the container's HMAC agent
# token. Builds on the ADK runtime image (google-adk + google-genai).
# =============================================================================

FROM robofleet-agent-adk

LABEL role="gemini-secretary"
LABEL description="Secretary on Gemini - a panel-driven ADK conversation"

# The in-container receiver the orchestrator delivers the CEO's turns to.
EXPOSE 9000

# Override the ADK one-shot entrypoint with the interactive secretary driver.
ENTRYPOINT ["python", "-m", "robofleet.agent_sdk.gemini_secretary_main"]