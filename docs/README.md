# Documentation index

Human-facing docs for RoboFleet. Several of the files below are being written in parallel by other agents as this index is written  -  if a link 404s right now, the file is still coming, index it anyway rather than dropping it.

| Doc | Covers | Audience |
|---|---|---|
| [`README.md`](../README.md) | What RoboFleet is, quickstart | New readers, GitHub landing page |
| [`docs/architecture.md`](architecture.md) | System architecture: orchestrator, Cloud Run agent spawn, panel, data stores | Engineers |
| [`docs/deploy.md`](deploy.md) | Deploying the GCP stack (Terraform, Cloud Run, Cloud SQL, Filestore) | Operators |
| [`docs/operations.md`](operations.md) | Running and operating a live deployment | Operators |
| [`docs/configuration.md`](configuration.md) | Environment variables and config reference | Operators, engineers |
| [`docs/lifecycle.md`](lifecycle.md) | The task state machine  -  statuses, transitions, roles | Engineers, agent-prompt authors |
| [`docs/agents.md`](agents.md) | The agent org chart  -  every role, team, and the `AGENTS` registry | Engineers, agent-prompt authors |
| [`docs/gateway.md`](gateway.md) | The gateway/Choreographer: intent verbs, the Envelope contract, per-role manifests | Engineers |
| [`docs/rag/`](rag/README.md) | The agent-facing knowledge-base corpus, indexed and served to spawned agents at runtime  -  see `docs/rag/README.md` for the indexing mechanism and its actual reach | Agents (via KB search/injection), and anyone editing what agents are told |

`docs/internal/` (gitignored) holds working notes and is not part of this index. `docs/architecture.svg` / `docs/architecture.png` are diagram sources referenced from `docs/architecture.md`.
