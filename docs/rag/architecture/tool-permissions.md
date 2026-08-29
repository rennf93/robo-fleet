# Tool Permissions by Role

## Overview

A delivery agent is a Google ADK `LlmAgent` on Gemini (Cloud Run Job execution, `robofleet.agent.adk_entry`). It has **no MCP servers of any kind** and no shell/Bash tool. Every tool it can call is an ADK `FunctionTool` built at spawn from exactly two sources plus a fixed git/file set:

| Mechanism | Provides |
|---|---|
| Flow verbs (`robofleet/agent/gateway_shim.py`, HTTP POST to `/api/v1/flow/{segment}/{verb}`) | Lifecycle verbs (`give_me_work`, `i_will_work_on`, `open_pr`, `complete`, ...) |
| Do-tools (HTTP POST to `/api/v1/do/{tool}`) | Content/write verbs (`commit`, `note`, `dm`, `notify`, `evidence`, ...) |
| Git/file ops (`robofleet/agent/git_tools.py`) | `read_file`, `write_file`, `delete_file`, `move_file`, `git_commit`, `git_status`, `git_push` - present on every role's tool list by construction, whether or not the role has a real workspace to point them at |

**There is no `robofleet-search` (web research), `robofleet-optimal` (KB/RAG), or `robofleet-docs` (docs store) tool surface reachable here at all** - those MCP servers exist in the codebase but are wired only for the legacy Docker/CLI-container provider path (`AgentOrchestrator._generate_mcp_config`), never for `ModelProvider.ADK_CLOUD_RUN`'s manifest builder (`_generate_adk_manifest`, which writes only `{flow_tools, do_tools, system_prompt}` from `role_config.py`). This means: no `web_search`/`web_fetch` for Board/PM roles regardless of `ROBOFLEET_RESEARCH_ENABLED`, no KB search of any kind for anyone, and documentation is written by committing a real file (`write_file` + `commit`), not through a docs-store API. See `docs/rag/README.md` and `docs/rag/tools/kb-tools.md` for the full explanation.

There is also **no `git_log`/`git_diff`/branch-listing tool** - only `git_status()` for porcelain status text. Native shell git is not "blocked by a hook" here; there is no shell tool to run it with at all. There is **no** `robofleet_git_commit / _push / _create_pr / _merge_pr / _checkout` tool either - write operations happen through the lifecycle verbs (`commit`, `open_pr`, `complete`) and the choreographer handles git as a side effect.

The canonical source of role -> verb mapping is `robofleet/services/gateway/role_config.py`; flow-verb membership is in turn generated from `robofleet/foundation/policy/lifecycle.py`'s `intents_for_role`. The tables below summarize it - see the individual role files under `docs/rag/roles/` for the fully worked-out tool surface per role.

## Developer

**Flow verbs:** `give_me_work`, `i_will_work_on`, `open_pr`, `i_am_done`, `i_am_blocked`, `unclaim`, `resume`, `sync_branch`, `i_am_idle`

**Do-tools:** `commit`, `note`, `dm`, `evidence`, `progress`, `pr_update`, `draft_playbook`, `propose_video`, `request_sandbox`, `request_render`, plus inbox tools

**Git/file ops:** all seven (`read_file`, `write_file`, `delete_file`, `move_file`, `git_commit`, `git_status`, `git_push`)

## QA

**Flow verbs:** `give_me_work`, `claim_review`, `pass`, `fail`, `i_am_blocked`, `unclaim`, `resume`, `i_am_idle`

**Do-tools:** `note`, `dm`, `evidence`, `draft_playbook`, `request_sandbox`, `request_render`, plus inbox tools (no `commit` - QA does not write code)

**Git/file ops:** present by construction, but QA carries no real write mandate - `read_file`/`git_status` are what it actually uses.

## Documenter

**Flow verbs:** `give_me_work`, `claim_doc_task`, `i_documented`, `i_am_blocked`, `unclaim`, `resume`, `i_am_idle`

**Do-tools:** `commit`, `note`, `dm`, `evidence`, `progress`, `pr_update`, `draft_playbook`, plus inbox tools

**Git/file ops:** all seven - documentation is written via `write_file` straight into the project's worktree, then `commit`.

## Cell PM

**Flow verbs:** `give_me_work`, `i_will_plan`, `delegate`, `declare_coverage`, `submit_up`, `triage`, `unblock`, `reassign`, `complete`, `request_changes`, `escalate_up`, `unclaim`, `resume`, `i_am_idle`

**Do-tools:** `note`, `dm`, `notify`, `evidence`, `pr_update`, `draft_playbook`, plus inbox tools (no `commit` - PMs delegate code; merging the leaf PR happens automatically inside `complete`)

**Git/file ops:** present by construction, not the sanctioned path for a PM.

## Main PM

**Flow verbs:** `triage`, `triage_all`, `give_me_work`, `i_will_plan`, `delegate`, `declare_coverage`, `unblock`, `submit_root`, `complete`, `request_changes`, `escalate_up`, `escalate_to_ceo`, `resume`, `unclaim`, `i_am_idle`

**Do-tools:** `note`, `dm`, `notify`, `evidence`, `pr_update`, `draft_playbook`, plus inbox tools

**Git/file ops:** present by construction, not the sanctioned path. `submit_root` on a root parent task opens the root->master PR (entering the `awaiting_pr_review` gate); after the main reviewer `pr_pass`es it, `complete` escalates to the CEO. The Main PM never merges to master - only the CEO does.

## Board (Product Owner, Head of Marketing)

Both share the same flow verbs; their do-tools diverge on the propose_* content verbs (see `docs/rag/roles/product-owner.md` and `docs/rag/roles/head-marketing.md` for the full lists).

**Flow verbs (both):** `triage`, `escalate_to_ceo`, `i_am_idle`

**Do-tools - Product Owner:** `note`, `pitch`, `dm`, `notify`, `evidence`, `nothing_to_propose`, `propose_roadmap`, `propose_bug_hunt`, `propose_gap_fill`, `propose_rebalance`, `propose_friction_fixes`

**Do-tools - Head of Marketing:** `note`, `pitch`, `dm`, `notify`, `evidence`, `nothing_to_propose`, `propose_feature_spotlight`, `propose_market_brief`, `propose_messaging_fixes`, `propose_editorial_post`, `propose_campaign`, `propose_conversation_replies`

**Web research:** none - neither role gets `web_search`/`web_fetch` under this runtime, `ROBOFLEET_RESEARCH_ENABLED` notwithstanding.

## Auditor

**Flow verbs:** `triage`, `waive_finding`, `i_am_idle` (read-only observation, one narrow write)

**Do-tools:** `note` (scope=reflect), `evidence`, `dm`, `read_a2a` (reply-only - it never initiates to a peer, so it still observes silently), `notify_list`, `notify_get`, `approve_playbook`, `reject_playbook`, `archive_playbook`, `curate_vault`, `propose_postmortem`, `propose_playbook_drafts`, `propose_quality_report`, `nothing_to_propose`

**Git/file ops:** carried by construction, unused - the Auditor writes nothing but a vault note (`curate_vault`) and reflection notes.

## PR Reviewer

**Flow verbs:** `give_me_work`, `claim_pr_review`, `post_pr_review` (inbound external/fork + internal PRs), `claim_gate_review`, `pr_pass`, `pr_fail` (in-path assembled-PR gate), `unclaim`, `i_am_idle` (read-only)

**Do-tools:** `note`, `evidence`, `dm`, `read_a2a`, `notify_list`, `notify_get` - the change-request itself is still posted server-side on the PR; `dm`/`read_a2a` exist so it can reply in-thread to a CEO-opened DM, and its only INITIATION target is its owning cell_pm/main_pm (the in-path gate verdict).

## Prompter (Intake) & Secretary

Both are human-only roles - they chat with the CEO, not other agents, and (unlike the delivery roles above) still run as interactive Gemini/Grok Docker containers with their own dedicated MCP servers (`robofleet-intake`, `robofleet-secretary`).

**Flow verbs:** `i_am_idle` only.

**Do-tools:** `note`, `evidence` only (no `dm` / `notify`).

## Tool Permissions Summary

| Capability | Dev | Doc | QA | Cell PM | Main PM | Board | Auditor |
|---|---|---|---|---|---|---|---|
| `commit` (writes code/docs) | Y | Y | - | - | - | - | - |
| `open_pr` (opens PR) | Y | - | - | - | - | - | - |
| `pass` / `fail` (QA verdict) | - | - | Y | - | - | - | - |
| `i_documented` | - | Y | - | - | - | - | - |
| `delegate` (creates subtasks) | - | - | - | Y | Y | - | - |
| `complete` (merges PR) | - | - | - | Y | Y | - | - |
| `escalate_to_ceo` | - | - | - | - | Y | Y | - |
| `notify` (ack-required) | - | - | - | Y | Y | Y | - |
| `dm` (A2A, initiate) | Y | Y | Y | Y | Y | Y | reply-only |
| `note` (journal entry) | Y | Y | Y | Y | Y | Y | Y (reflect) |
| web research / KB search | - | - | - | - | - | - | - |

Web research and KB search are unavailable to every role, deliberately - see the Overview above.

**CEO** is human and never inside an agent container; the panel runs as the CEO via `X-Agent-Role: ceo` against the orchestrator API directly.
