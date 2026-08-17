# Gemini/ADK Intake (Prompter) Agent - interactive ADK session on Gemini.
# =============================================================================
# The Gemini analogue of agent-grok-prompter. Holds a PERSISTENT conversation:
# receives the human's messages over HTTP (POST /turn on :9000) and, per turn,
# runs one ADK Runner turn over a persistent InMemorySessionService session on
# Gemini 3.5 Flash, streaming each reply back to the panel via the relay (see
# robofleet.agent_sdk.gemini_intake_main + gemini_chat_session). The intake
# propose_draft / propose_batch / search_past_tasks tools are wired as the
# robofleet-intake MCP server via an ADK McpToolset (stdio subprocess). Builds
# on the ADK runtime image (google-adk + google-genai, no Claude CLI, no Node).
# =============================================================================

FROM robofleet-agent-adk

LABEL role="gemini-prompter"
LABEL description="Intake interviewer on Gemini - a panel-driven ADK conversation"

# The in-container receiver the orchestrator delivers the human's turns to.
EXPOSE 9000

# Override the ADK one-shot entrypoint with the interactive intake driver.
ENTRYPOINT ["python", "-m", "robofleet.agent_sdk.gemini_intake_main"]