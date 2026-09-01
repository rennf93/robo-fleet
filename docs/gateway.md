# The Gateway

Agents never call the database, the task API, or the forge directly. Every action goes through the **Choreographer** (`robofleet/services/gateway/choreographer/`), reached over one HTTP surface: `POST /api/v1/flow/{segment}/{verb}` for intent (flow) verbs and `POST /api/v1/do/{tool}` for content (do) tools. The Choreographer composes the underlying services (`TaskService`, `GitService`, `JournalService`, ...) into atomic verb sequences, and every call returns the same standardized **Envelope** shape.

## Auth

Every request carries `X-Agent-ID` (the caller's UUID), `X-Agent-Role`, and — when signed — `X-Agent-Team` and `X-Agent-Token` (an HMAC signed over id+role+team; `robofleet/agent/gateway_shim.py`, `robofleet/agent/adk_entry.py`). The route layer resolves a role-gated FastAPI dependency (e.g. `require_dev` on every `/api/v1/flow/developer/*` route, `robofleet/api/routes/v1/flow_dev.py`) before the handler ever reaches the Choreographer — a QA agent's token cannot hit a developer-only route regardless of what the lifecycle spec would say.

## Route segments

Each role's flow verbs live under its own route prefix (`robofleet/api/routes/v1/flow_*.py`):

| Segment | Path prefix | Roles |
|---|---|---|
| `developer` | `/api/v1/flow/developer` | `developer` |
| `qa` | `/api/v1/flow/qa` | `qa` |
| `documenter` | `/api/v1/flow/documenter` | `documenter` |
| `cell_pm` | `/api/v1/flow/cell_pm` | `cell_pm` |
| `main_pm` | `/api/v1/flow/main_pm` | `main_pm` |
| `board` | `/api/v1/flow/board` | `product_owner`, `head_marketing` (share one segment) |
| `auditor` | `/api/v1/flow/auditor` | `auditor` |
| `pr_reviewer` | `/api/v1/flow/pr_reviewer` | `pr_reviewer` |

Content tools all live under one segment: `POST /api/v1/do/{tool}` (`robofleet/api/routes/v1/do.py`).

## The Envelope

`robofleet/services/gateway/envelope.py`. Every verb returns this dataclass, serialized via `as_dict()`.

**Success** (`Envelope.ok`):

```json
{
  "status": "awaiting_qa",
  "task_id": "9e221faf-...",
  "next": "idle - PM will resolve and notify",
  "evidence": { "...": "verb-specific payload" },
  "context_briefing": { "...": "institutional_memory, company_goals, etc." },
  "error": null,
  "correlation_id": "...",
  "current_state": "awaiting_qa",
  "valid_next_verbs": ["give_me_work", "i_am_idle", "..."]
}
```

**Error** — one of seven flavors, each a classmethod on `Envelope`:

| Constructor | `error` value | When |
|---|---|---|
| `Envelope.tracing_gap` | `tracing_gap` | a declarative `Precondition` failed (missing plan, no commits, etc.) |
| `Envelope.incomplete_input` | `incomplete_input` | under-filled input fields; carries `field_hints`, a literal answer-key |
| `Envelope.invalid_state` | `invalid_state` | the task isn't in a state this verb accepts |
| `Envelope.not_authorized` | `not_authorized` | role/ownership/self-review violation |
| `Envelope.not_found` | `not_found` | the task or agent doesn't resolve |
| `Envelope.sequence_held` | `sequence_held` | a same-parent sibling with lower sequence still holds the claim (see `docs/lifecycle.md`) |
| `Envelope.circuit_open` | `circuit_open` | a per-verb retry breaker tripped (wired by the agent-runtime tracker, not the gateway itself) |

Every error carries `message` (never null — `_missing_message` folds the missing tokens and the `remediate` hint into one line even when a caller only reads `message`) and `remediate` (the exact next call to make). `Envelope.from_decision` maps a lifecycle-spec `Decision` rejection onto the right flavor automatically. `with_introspection(task, role)` — called on nearly every response, success or failure — stamps `current_state` and `valid_next_verbs` so an agent never has to guess what it can legally call next; it fails silently to `[]` rather than ever raising.

## How remediation works

`robofleet/services/gateway/remediation.py` holds one function per common gap, each returning a concrete, copy-pasteable next call — not a generic "fix your input" message. Examples actually in the code:

- Missing progress before `i_am_done`: *"make at least one commit (use `commit(message=...)`) before `i_am_done`; the commit auto-creates a progress entry."*
- Open revision findings blocking `i_am_done`: *"...call `i_am_done(resolved_findings=[{'finding_id': '<id>', 'commit': '<sha>', 'note': '<what you changed>'}, ...])` naming every id (the id shown is the 8-char prefix from the `[F-xxxxxxxx]` rendering in your qa_notes/pm_notes/pr_reviewer_notes)."*
- Missing AC coverage on `delegate`: renders the exact corrected call with real acceptance-criteria ids/text inlined, not a placeholder.

## The Choreographer's composition model

`VerbRunner.run_intent` (`robofleet/services/gateway/choreographer/_verb_runner.py`) is the shared runner behind every composed verb:

1. **`pre_side_effects`** run first, outside the DB transaction — e.g. `submit_up` opens the cell→root PR (`create_pr`) *before* the `submit_for_review` transition, so the downstream `pr_created` gate is already satisfied by the time it's checked.
2. **Composed atomic actions** run inside one `session.begin_nested()` savepoint — a mid-sequence failure rolls the whole verb back to its pre-call state.
3. **`side_effects`** run after the savepoint commits (git push, PR creation for verbs that don't need it upfront), each independently idempotent/retryable.

Claim-time concurrency invariants (`already_active`, `paused`, `sequence_held`, `unmet_dependency`, `project_budget_exceeded`) run in `claim_guards.py` before any of this — see `docs/lifecycle.md`.

## Flow verbs and content tools per role

Generated directly from `robofleet.services.gateway.role_config.ROLE_CONFIGS`, itself thin sugar over `lifecycle.intents_for_role` (flow) plus a hand-maintained content-tool tuple (do):

| Role | Flow verbs | Do tools | Writes to workspace |
|---|---|---|---|
| `developer` | `give_me_work`, `i_am_blocked`, `i_am_done`, `i_am_idle`, `i_will_work_on`, `open_pr`, `resume`, `sync_branch`, `unclaim` | `commit`, `note`, `dm`, `evidence`, `progress`, `pr_update`, `draft_playbook`, `propose_video`\*, `request_sandbox`\*, `request_render`\*, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a` | yes |
| `qa` | `claim_review`, `fail_review`, `give_me_work`, `i_am_blocked`, `i_am_idle`, `pass_review`, `resume`, `unclaim` | `note`, `dm`, `evidence`, `draft_playbook`, `request_sandbox`\*, `request_render`\*, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a` | no |
| `documenter` | `claim_doc_task`, `give_me_work`, `i_am_blocked`, `i_am_idle`, `i_documented`, `resume`, `unclaim` | `commit`, `note`, `dm`, `evidence`, `progress`, `pr_update`, `draft_playbook`, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a` | yes |
| `cell_pm` | `complete`, `declare_coverage`, `delegate`, `escalate_up`, `give_me_work`, `i_am_idle`, `i_will_plan`, `reassign`, `request_changes`, `resume`, `submit_up`, `triage`, `unblock`, `unclaim` | `note`, `dm`, `notify`, `evidence`, `pr_update`, `draft_playbook`, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a` | no |
| `main_pm` | `complete`, `declare_coverage`, `delegate`, `escalate_to_ceo`, `escalate_up`, `give_me_work`, `i_am_idle`, `i_will_plan`, `request_changes`, `resume`, `submit_root`, `triage`, `triage_all`, `unblock`, `unclaim` | `note`, `dm`, `notify`, `evidence`, `pr_update`, `draft_playbook`, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a` | no |
| `product_owner` | `escalate_to_ceo`, `i_am_idle`, `triage` | `note`, `pitch`, `dm`, `notify`, `evidence`, `nothing_to_propose`, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a`, `propose_roadmap`\*, `propose_bug_hunt`\*, `propose_gap_fill`\*, `propose_rebalance`\*, `propose_friction_fixes`\* | no |
| `head_marketing` | `escalate_to_ceo`, `i_am_idle`, `triage` | `note`, `pitch`, `dm`, `notify`, `evidence`, `nothing_to_propose`, `notify_list`, `notify_get`, `notify_ack`, `read_messages`, `read_a2a`, `propose_feature_spotlight`\*, `propose_market_brief`\*, `propose_messaging_fixes`\*, `propose_editorial_post`\*, `propose_campaign`\*, `propose_conversation_replies`\* | no |
| `auditor` | `i_am_idle`, `triage`, `waive_finding` | `note`, `evidence`, `dm`, `read_a2a`, `approve_playbook`, `reject_playbook`, `archive_playbook`, `curate_vault`\*, `propose_postmortem`\*, `nothing_to_propose`, `notify_list`, `notify_get`, `propose_quality_report`\*, `propose_playbook_drafts`\* | no |
| `pr_reviewer` | `claim_gate_review`, `claim_pr_review`, `give_me_work`, `i_am_idle`, `post_pr_review`, `pr_fail`, `pr_pass`, `unclaim` | `note`, `evidence`, `dm`, `read_a2a`, `notify_list`, `notify_get` | no |
| `prompter` | `i_am_idle` | `note`, `evidence` | no |
| `secretary` | `i_am_idle` | `note`, `evidence` | no |

\* Backed by a subsystem that is default-off / unarmed on this deployment (see "Inert tools" below) — the manifest carries the tool declaratively, but the underlying feature is gated shut.

Every role also implicitly gets `i_am_idle` (`intents_for_role` guarantees it). `product_owner`/`head_marketing` also carry `pitch` in the do-tool set for a separate CEO-approved provisioning flow, not detailed here.

## How a spawned ADK agent reaches the gateway

**There are no MCP servers on this path.** The repo still ships `robofleet/mcp/flow_server.py`, `do_server.py`, `git_readonly.py`, and friends — these back the inherited Claude-Code-CLI container spawn path (`robofleet/llm/providers/claude_code.py`): the orchestrator builds an `mcpServers` config that has Claude Code itself launch each server as `uv run python -m robofleet.mcp.<server>` inside the container, exposed as `mcp__robofleet-flow__*` / `mcp__robofleet-do__*` tools — the same convention the role prompts under `agents/prompts/roles/*.md` still describe. The GCP path is different: `robofleet/runtime/orchestrator.py` states it explicitly — *"ADK agents have no MCP servers: the gateway shim calls the orchestrator HTTP directly."*

The actual flow (`robofleet/agent/adk_entry.py` + `robofleet/agent/gateway_shim.py`):

1. `adk_entry.main()` reads the manifest (`/app/tool-manifest.json`, or a `gs://` blob — the same manifest `_build_manifest_for_agent` in `orchestrator.py` writes per spawn) and builds one ADK `FunctionTool` per verb/tool name it lists, via `build_gateway_tools()`.
2. Each tool is either a hand-written function with a real typed signature (`_SPECIALIZED` in `gateway_shim.py` — needed because ADK derives a tool's JSON schema from the Python function signature, and the manifest itself carries only bare verb names) or a generic `**kwargs` passthrough for the handful of truly argument-less verbs (`give_me_work`, `i_am_idle`, `triage`).
3. Calling a flow tool POSTs to `{orchestrator_base}/api/v1/flow/{segment}/{verb}`; a do tool POSTs to `{orchestrator_base}/api/v1/do/{tool}`. `call_verb`/`call_do` remap two intent names to their public route names (`pass_review`→`pass`, `fail_review`→`fail`); every other verb's manifest name is already the public route name.
4. The orchestrator base URL self-corrects for the Cloud Run Job's network position: an injected `ROBOFLEET_ORCHESTRATOR_URL` that resolves to a docker-mesh-only host (`localhost` / `robofleet-orchestrator` / `127.*`) is swapped for a public Cloud Run URL (`ROBOFLEET_PUBLIC_API_URL`), since a Cloud Run Job container is not on the same network as a docker-compose deploy would be.
5. The JSON response is handed straight back to the model as the tool result. A non-JSON or envelope-shapeless response is synthesized into a `{"error": "transport", ...}` envelope rather than crashing the tool call.
6. Separately, `build_git_tools()` (`robofleet/agent/git_tools.py`) registers seven raw FunctionTools — `read_file`, `write_file`, `delete_file`, `move_file`, `git_commit`, `git_status`, `git_push` — that operate directly on the agent's mounted worktree (`ROBOFLEET_WORKSPACE_DIR`), independent of the manifest and independent of role. `git_commit` here is a raw local commit with no task-id prefix and no `TaskService` linkage — the gateway's own `commit` do-tool (which stamps `[{task_id[:8]}] ...` and records a progress entry) is the one that actually threads through the lifecycle. `LlmAgent`'s final tool list is `build_gateway_tools() + build_git_tools()` — every ADK agent gets all seven raw git/file tools regardless of its `role_config.allows_write` value; `allows_write` is consulted only by the (unused-on-GCP) Claude-Code/grok/gemini/codex/kimi CLI paths to decide whether to grant `Edit`/`Write`.

## Inert tools

`propose_roadmap`, `propose_bug_hunt`, `propose_gap_fill`, `propose_rebalance`, `propose_friction_fixes`, `propose_feature_spotlight`, `propose_market_brief`, `propose_messaging_fixes`, `propose_editorial_post`, `propose_campaign`, `propose_conversation_replies`, `propose_postmortem`, `propose_quality_report`, `propose_playbook_drafts`, `curate_vault`, `request_sandbox`, `request_render`, and `propose_video` are all declared in the manifest for their roles, but each backs a "Board Program" or infrastructure subsystem (weekly roadmap cycles, an X/Twitter drafting queue, an Obsidian vault writer, on-demand sandbox DB provisioning, the video-render pipeline) gated by its own default-off flag in `robofleet/config.py`. Calling one on this deployment either no-ops or returns a clean rejection from the underlying feature-flag check — not a 404, since the tool is genuinely registered, just gated shut.
