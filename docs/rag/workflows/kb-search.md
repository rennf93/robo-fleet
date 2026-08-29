# Knowledge Base Search

**No agent has access to KB/RAG tools under the current runtime.** `robofleet_ask_mentor`, `robofleet_kb_search`, `robofleet_rag_query`, and `robofleet_get_proactive_context` are real MCP tools (`robofleet/mcp/optimal_server.py`) but they are mounted only for the legacy Docker/CLI-container provider path  -  never for `ModelProvider.ADK_CLOUD_RUN`, the runtime every delivery agent (dev/qa/doc/pm/pr-reviewer/board) actually spawns on. See `docs/rag/README.md` and `docs/rag/tools/kb-tools.md` for the full mechanism and why.

## What you actually have instead

Nothing that searches the knowledge base. Work from:

- What the task prompt already handed you (composed at spawn from `compose_prompt` + the conventions ambient block)
- What your flow verbs return inline (`evidence(task_id)`, `claim_review`'s AC/PR data, `context_briefing` on claim)
- `read_file` over your actual worktree, when you have one

The one automatic path back to KB-derived content is the org-memory "institutional memory" briefing (`context_briefing["institutional_memory"]`), injected at claim time when `org_memory_enabled` is armed (default off) - and even then it only covers the `LEARNINGS`/`PLAYBOOKS` indexes, never `DOCUMENTATION`/`code`. You never call anything to get it.

## Before Starting a Task

There is no pre-task KB search step to run - skip straight to `give_me_work()`/`i_will_work_on(...)` and rely on the task's own acceptance criteria and whatever context arrives with it.
