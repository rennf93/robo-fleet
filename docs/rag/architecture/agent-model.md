# Agent Model

## Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `name` | String | Display name |
| `slug` | String | URL-safe ID (e.g., `be-dev-1`) |
| `role` | Enum | Agent role |
| `team` | Enum | Team affiliation |
| `status` | Enum | active, idle, offline |

## Roles

| Role | Description |
|------|-------------|
| `ceo` | Human executive |
| `product_owner` | Product strategy |
| `head_marketing` | External comms |
| `auditor` | Silent observer |
| `main_pm` | Coordinates all cells |
| `cell_pm` | Manages one cell |
| `developer` | Writes code |
| `qa` | Reviews and tests |
| `documenter` | Writes documentation |
| `pr_reviewer` | Read-only reviewer: inbound external/fork + internal PRs, and the in-path assembled-PR gate (`pr-reviewer-1` main + `be/fe/ux-pr-reviewer` per cell) |
| `prompter` | On-demand intake interviewer, human-only (agent `intake-1`) |
| `secretary` | On-demand chief-of-staff, human-only (agent `secretary-1`) |
| `system` | Internal orchestrator |

## Teams

| Team | Agents |
|------|--------|
| `backend` | be-pm, be-dev-*, be-qa, be-doc, be-pr-reviewer |
| `frontend` | fe-pm, fe-dev-*, fe-qa, fe-doc, fe-pr-reviewer |
| `ux_ui` | ux-pm, ux-dev-*, ux-qa, ux-doc, ux-pr-reviewer |
| `main_pm` | main-pm |
| `board` | product-owner, head-marketing, auditor |
| `marketing` | head-marketing |

## Status

| Status | Meaning |
|--------|---------|
| `active` | Currently working |
| `idle` | Available for work |
| `offline` | Not available |

## Capabilities

Example capabilities:
- `code_execution`
- `git_operations`
- `documentation`
- `testing`

## Model Configuration

Stored in `model_config` JSON:
- LLM provider
- Model name
- Temperature
- Other settings

The **provider** selects the agent backend, resolved through the `ProviderRegistry` (`robofleet/llm/providers/`). `ModelProvider` is `ADK_CLOUD_RUN` (the live delivery spawn path  -  Google ADK + Gemini as a Cloud Run Job, `robofleet.agent.adk_entry`, see `docs/rag/README.md`), `ANTHROPIC`, `OLLAMA_CLOUD`, `OPENAI` (OpenAI's official `codex` CLI, ChatGPT subscription), `LOCAL`, `GROK` (xAI's official `grok` CLI, model `grok-build`, on a SuperGrok subscription), `KIMI` (Moonshot's official `kimi`/kimi-code CLI, Kimi subscription via OAuth device-code login), or `GEMINI` (Google's official `gemini` CLI, OAuth login  -  the CLI provider, distinct from `ADK_CLOUD_RUN`'s direct `google-adk` runtime). **A delivery agent (dev/qa/doc/pm/pr-reviewer/board) with no registered provider for its `provider_type` fails to spawn outright**  -  the Claude-CLI-in-Docker spawn path for delivery roles was removed ("Leg D1"); `AgentOrchestrator._spawn_container` raises `"No spawn backend for provider ...: The Claude CLI runtime was removed; use ADK_CLOUD_RUN."` Codex, the Gemini CLI, and Kimi are one-shot delivery-role-capable runtimes in principle (no Intake/Secretary) but are not the default; Grok additionally drives the interactive Intake and Secretary chats, and Gemini (via its own dedicated `agent-gemini-prompter`/`-secretary` images) does too. Grok's `~/.grok` is auto-refreshed by the orchestrator; Kimi's `~/.kimi-code` is mounted read-write and shared across every Kimi agent, since Moonshot's refresh token is rotation-with-short-reuse-grace and every container redeems the same rotating chain. Kimi runs headless via `-p` with stream-json output, scopes tools through rendered deny-rules plus a `PreToolUse` bash-guard wrapper hook (no CLI-flag tool-removal equivalent), captures usage by summing `wire.jsonl`'s token buckets, and parks on rate-limit (exit 75) or an expired/missing credential (exit 78) exactly like Grok/Codex/Gemini/ADK so the orchestrator can pause and later revive it.

## Agent-Specific Fields

| Field | Description |
|-------|-------------|
| `current_task_id` | Currently assigned task |
| `journal_id` | Personal journal |
| `system_prompt` | Base prompt |
| `permissions` | Tool/verb permission scope |
| `metrics` | Performance data |
