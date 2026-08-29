# RAG knowledge-base corpus

This directory is read at runtime, not just by humans: it is auto-indexed into RoboFleet's knowledge base and is meant to be served back to agents. Wrong content here actively misleads the fleet  -  treat every claim as load-bearing.

## How indexing actually works

`OptimalService` (`robofleet/services/optimal.py`) auto-indexes one directory under `docs/`: `AUTO_INDEX_DIRS = ("rag",)` (line 67). At startup (`_auto_index_on_startup` -> `_auto_index_docs`) it walks `docs_root/rag` recursively for every `*.md` file and indexes it (`_index_docs_directory`, `.rglob("*.md")`)  -  every file below this README, at any depth, is picked up, including this file itself and everything under `lifecycle/`. A file under a `standards/` subdir routes to a dedicated standards indexer instead of the general documentation indexer (`_index_doc_file`, `is_standards = name == "standards" or "standards" in md_file.parts`); everything else lands in `IndexType.DOCUMENTATION`. When `rag_auto_update_enabled` (default `true`), a background loop re-scans every `rag_auto_update_interval` seconds (default `300`) for new/modified/deleted files and re-indexes or de-indexes them (`_periodic_update_loop` -> `_check_for_updates`)  -  a saved edit here reaches the KB within minutes, no restart needed. A file deleted while the process was down is reconciled once at the next startup (`_reconcile_deleted_docs_from_db`).

## What actually reaches a spawned agent (read this before assuming search works)

Indexing is necessary but **not sufficient** for a delivery agent to see this content. The MCP tools that search it  -  `robofleet_kb_search`, `robofleet_ask_mentor`, `robofleet_rag_query` (`robofleet/mcp/optimal_server.py`, mounted as the `robofleet-optimal` MCP server)  -  are wired for the legacy Docker/CLI-container provider path (`robofleet/runtime/orchestrator.py`, the generic MCP-mounting block). **The default delivery runtime does not use it.** A dev/QA/PM/documenter/PR-reviewer/board agent is spawned via `ModelProvider.ADK_CLOUD_RUN` (`robofleet.agent.adk_entry`, a Google ADK `LlmAgent`), and that entrypoint builds its tools from exactly two sources  -  `build_gateway_tools()` (`robofleet/agent/gateway_shim.py`, HTTP-routed flow/do verbs) and `build_git_tools()` (`robofleet/agent/git_tools.py`)  -  neither of which includes any KB-search tool. The `agent-adk.Dockerfile` says it plainly: "No MCP servers (the shim calls the orchestrator HTTP directly)." Confirmed by `role_config.py`: no role's `do_tools` tuple contains `kb_search` or `ask_mentor`.

The one automatic path this corpus (specifically `DOCUMENTATION`-indexed content, i.e. everything here) could still reach an agent through is the org-memory "institutional memory" briefing injected at claim time (`Choreographer._institutional_memory`)  -  but that mechanism queries the `LEARNINGS` + `PLAYBOOKS` indexes only (`EvidenceRepo.similar_memory`), not `DOCUMENTATION`, and it is gated behind `org_memory_enabled` (default off). So as currently wired, **this corpus is indexed but not reachable by an ADK-spawned delivery agent through any tool call or automatic injection.** It IS reachable by the interactive Intake/Secretary Gemini-CLI agents' own MCP servers if those ever mount `robofleet-optimal` (check `robofleet/mcp/intake_server.py` / `secretary_server.py` before assuming  -  at last check neither did), and by anything else in the codebase that still spawns through a legacy Docker/CLI provider. If you are adding a KB-search tool to the ADK path, wire it the same way `gateway_shim.py` wires everything else (an HTTP route + a `FunctionTool`), not as an MCP mount.

## Structure

```
docs/rag/
+-- README.md          this file
+-- roles/              per-role responsibilities and gateway-verb surface
+-- lifecycle/          GENERATED  -  do not hand-edit, see below
+-- tools/              the real tool surface: gateway verbs, do-tools, git_tools
+-- troubleshooting/    symptom -> cause -> fix, keyed to the actual ADK constraints
+-- workflows/          step-by-step task flows (git, QA, escalation, MegaTask, ...)
+-- architecture/       system components, data model, policy
+-- standards/          coding, security, testing rules (routed to a separate index)
```

`lifecycle/intent-verbs.md` and `lifecycle/status-transitions.md` are **generated** by `scripts/build_lifecycle_artifacts.py` from `robofleet/foundation/policy/lifecycle.py` (run via `make lifecycle`, checked by `make foundation-check`). Never hand-edit them  -  edit the spec and regenerate.

## Editing this corpus

One topic per file, self-contained (an agent retrieves a chunk, not the whole tree). Prioritize the files a delivery agent's own role/verb/troubleshooting questions actually hit  -  `roles/`, `tools/`, `troubleshooting/`  -  over exhaustive architecture prose. A smaller true file beats a larger stale one: every claim here should be traceable to code you actually read in this repo, not carried over from the predecessor product or from what would be true under a different agent runtime.
