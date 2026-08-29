# Knowledge Base Troubleshooting

**None of the errors this file used to troubleshoot can occur for a spawned delivery agent under the current runtime, because none of the underlying tools (`robofleet_kb_search`, `robofleet_rag_query`, `robofleet_ask_mentor`, `robofleet_kb_stats`, `robofleet_docs_*`, `robofleet_kb_index_*`) are reachable at all.** They exist server-side (`robofleet/mcp/optimal_server.py`, `robofleet/mcp/docs_server.py`) but are mounted only for the legacy Docker/CLI-container provider path, never for the ADK Cloud Run runtime this fleet's delivery agents run on. See `docs/rag/tools/kb-tools.md` and `docs/rag/README.md` for the full explanation.

If you are an agent reading this because a KB call "didn't work": it isn't erroring, it simply is not one of your tools - check your manifest (the tools actually offered to you at spawn) rather than retrying a call that will never appear there. There is no reindex/clear-index operation available to you either.

If you are extending this codebase to add KB access to the ADK path, that is a code change (a new `FunctionTool` in `robofleet/agent/gateway_shim.py` plus a `do_tools` entry in `role_config.py`), not something to work around from inside an agent.
