# CLAUDE.md

Guidance for a coding agent working on **this** repository.

## What this is

RoboFleet  -  an AI Agentic Company: a virtual org of AI agents (developers, QA, PMs, documenters, PR reviewers, a Board) that plans, codes, reviews, and ships work through a real git/PR lifecycle, coordinated by a FastAPI orchestrator with a Next.js control panel. This is a GCP port of a predecessor homelab product ("RoboCo"); the predecessor's docs were deleted on purpose  -  do not resurrect them from git history, and do not describe NAS/homelab/Olares deployment here, none of that applies to this repo.

**Delivery-agent runtime: Google ADK + Gemini on Cloud Run Jobs.** A delivery agent (dev/qa/doc/pm/pr-reviewer/board) is spawned as a Cloud Run Job execution (`CloudRunJobsProvider`, `robofleet/llm/providers/cloudrun_jobs.py`, `ModelProvider.ADK_CLOUD_RUN`) running `robofleet.agent.adk_entry`  -  a `google.adk` `LlmAgent` on Gemini (`ROBOFLEET_AGENT_MODEL`, default `gemini-3.5-flash`). **It has no MCP servers and no shell/Bash tool**  -  its only tools are `FunctionTool`s built at spawn from the role's manifest: gateway verbs (`robofleet/agent/gateway_shim.py`, HTTP POSTs to the orchestrator's `/api/v1/flow/{segment}/{verb}` and `/api/v1/do/{tool}`) plus git/file ops over its worktree (`robofleet/agent/git_tools.py`: `read_file`/`write_file`/`delete_file`/`move_file`/`git_commit`/`git_status`/`git_push`  -  no `git_log`/`git_diff`/branch listing). The interactive Intake and Secretary roles are the exception: they still run as local Docker containers (Gemini or Grok CLI) with their own dedicated MCP servers (`robofleet-intake`, `robofleet-secretary`). Other provider registrations (Grok/Codex/Kimi/legacy Gemini-CLI) still exist in `robofleet/llm/providers/` for those interactive roles and for non-default routing; they are not the delivery path. The plain Claude-CLI-in-Docker spawn path for delivery roles was removed  -  `_spawn_container` raises if a delivery agent resolves to no registered provider.

## Directory layout

```
robofleet/          the application package (see below)
panel/               Next.js control panel (pnpm workspace, own CLAUDE.md/AGENTS.md)
alembic/             DB migrations (alembic/versions/, ~95 files at last count)
agents/prompts/      composed agent system-prompt layers (base/roles/teams/identities/
                     doctrine) + agents/prompts/_generated/ (regenerated, see below)
docker/              one Dockerfile per agent runtime (agent-adk, agent-gemini*,
                     agent-grok*, agent-codex, agent-kimi) + orchestrator/panel/nginx
infra/               Terraform + gcloud deploy scripts for the GCP stack
motion/, video-renderer/   the video/motion-graphics subsystem
tests/               compliance/ e2e_smoke/ fixtures/ foundation/ integration/
                     property/ unit/
scripts/             build_lifecycle_artifacts.py, regenerate_verb_tables.py,
                     reflow_md.py, verify_postgres_enums.py, bootstrap.sh
.robofleet/          conventions.yml (architectural conventions standard, see below)
```

Inside `robofleet/`: `agent/` (ADK entrypoint + tool shims), `agent_sdk/` (interactive Gemini/Grok session drivers for Intake/Secretary), `api/` (FastAPI routes/schemas), `foundation/` (`identity.py`  -  the single `AGENTS` registry; `policy/`  -  pure policy modules, `lifecycle.py` is canonical), `services/` (business logic; `services/gateway/` is the Choreographer that composes services into intent verbs), `llm/providers/` (per-provider agent spawn backends), `mcp/` (the MCP servers used by Intake/Secretary and by non-ADK providers, not by ADK delivery agents), `models/`, `db/`, `runtime/` (`orchestrator.py`), `conventions/` (the architecture-standard validator), `eval/`, `billing/`, `vault.py` (Obsidian vault integration).

## Package name and config

The importable package is **`robofleet`** (`pyproject.toml` `[project] name`). `Settings` (`robofleet/config.py`) loads from environment variables prefixed **`ROBOFLEET_`** (`env_prefix="ROBOFLEET_"`, `.env` file), e.g. `ROBOFLEET_AGENT_MODEL`, `ROBOFLEET_GCP_PROJECT_ID`, `ROBOFLEET_WORKSPACES_ROOT`. CLI entry points: `robofleet` (`robofleet.cli:cli`), `robofleet-bootstrap` (`robofleet.bootstrap:cli`).

## Running the gate, tests, and lint

Everything below is a real `Makefile` target  -  verify with `make help` or the Makefile itself before trusting anything not listed here.

- `make sync`  -  `uv sync --extra dev` (the `dev` extra carries ruff/mypy/pytest/vulture/bandit/radon/xenon/deptry/import-linter  -  plain `uv sync` skips them).
- `make quality`  -  **the merge gate**, run this before considering work done. Chains: compose-file sync check, `ruff format --check`, `ruff check`, markdown-prose reflow check, `mypy robofleet/ tests/`, `pytest --cov=robofleet --cov-fail-under=80`, `xenon --max-absolute B --max-modules A --max-average A robofleet/`, `radon mi`, `vulture --min-confidence 100`, `bandit -r robofleet/ -ll`, `pip-audit` (one documented CVE waiver, see the Makefile), `deptry robofleet/`, `alembic upgrade head --sql` (migrations parse), `lint-imports` (import-linter boundary contracts, see `pyproject.toml` `[tool.importlinter]`), and `make foundation-check`.
- `make gate`  -  the fast pre-submit subset (format/lint/types/xenon/import-linter, **no tests**)  -  this is what a dev agent's own `i_am_done` pre-submit check runs.
- `make lint` / `make fix`  -  ruff format+check / mypy / vulture; `fix` auto-fixes what ruff can.
- `make foundation-check`  -  validates `foundation/identity.py`, runs the `tests/foundation/` suite, and **regenerates the lifecycle artifacts** (`make lifecycle`) and verb tables, failing on any git diff. Run `make lifecycle` yourself and commit the diff after touching `robofleet/foundation/policy/lifecycle.py`  -  it rewrites `docs/rag/lifecycle/intent-verbs.md`, `docs/rag/lifecycle/status-transitions.md`, `panel/lib/lifecycle.json`, and `agents/prompts/_generated/lifecycle-{role}.md`. Never hand-edit those five generated targets.
- `make e2e-smoke`  -  the scripted-agent lifecycle smoke test: real gateway verbs/gates against an in-process API + ephemeral Postgres + local git origin, no LLM. CI-only job, excluded from `make quality`.
- `make migrate`  -  `alembic upgrade head`. `make migration`  -  interactive `alembic revision --autogenerate -m "<message>"`.
- `make infra` / `make infra-down`  -  Postgres + Redis via `docker compose` (needed for anything that touches the DB, including most of `make quality`'s pytest run).
- `make panel-gate`  -  `pnpm lint && pnpm exec tsc --noEmit && pnpm test` inside `panel/`; run this instead of the Python gate for panel-only changes.
- **Do not use** `make test`, `make test-all`, `make stress-test`, or `make high-load-stress-test`  -  they run `docker compose run ... robo-fleet` / `robofleet-example`, service names that do not exist in `docker-compose.yml` (leftover template targets). Use `make quality` or `uv run pytest <path>` directly.

## Migrations

Alembic, single head, under `alembic/versions/`, numbered sequentially (`077_github_app.py` … `095_verb_latency_samples.py` at last count  -  check the newest file for the next number). `make migration` scaffolds one via autogenerate; hand-check it before committing. `make quality` only verifies migrations *parse* (`alembic upgrade head --sql`)  -  run `make migrate` against a live `make infra` Postgres to verify they actually apply.

## Branch and commit conventions

Branch names: `{type}/{team}/{root_short}--{sub_short}--{subsub_short}` (`robofleet/templates/git/branch.py`)  -  `type` is one of `feature`, `bug`, `chore`, `docs`, `hotfix`; each `*_short` is the task UUID's first 8 chars; `--` (not `/`) separates hierarchy levels to avoid git ref collisions; max 4 levels deep. Branches are auto-created on task claim  -  do not hand-create them.

Commits are auto-prefixed `[{task_id:8}] {your subject}` by the gateway's `commit()` action (`robofleet/services/gateway/content_actions.py`), which validates the subject via `commit_validator.validate_commit_message`: must be non-empty, >=20 chars (`commit_subject_min_chars`), and not a single banned word (`wip`, `tmp`, `asdf`, `oops`, `fix`, `update`, `change`, `stuff`, `things`). Conventional-Commits shape (`type(scope): subject`) is a soft hint on mismatch, not enforced. Only `developer` and `documenter` roles may commit.

## Architectural conventions standard

`.robofleet/conventions.yml` declares module ownership for both layers (`robofleet/models`, `robofleet/api`, `robofleet/api/routes`, `robofleet/services`, `robofleet/utils`, and the `panel/src/{components, hooks, store, lib}` mirror) plus rule-level policy (`no_inline_comments`, `no_lint_suppressions`, `thin_routes`, `thin_components`  -  currently `warn`, with reasons in-file) and per-path waivers. It overlays an auto-derived scan (`robofleet/conventions/`, tree-sitter-based Python+TS validator)  -  a misplaced *helper* only warns, a misplaced model/route/component blocks. No `# noqa` / `# type: ignore` beyond the auto-allowed framework codes (`TC001`-`TC003`, pydantic `prop-decorator`); a genuine false positive needs a reviewed waiver entry in this file, never an inline suppression.

## Licensing

AGPL-3.0 (`LICENSE`). Do not reintroduce an MIT or other license reference anywhere. Contributions require a signed CLA (`CLA.md`, see `CONTRIBUTING.md`); keep copyright-assignment language intact.

## Docs

`docs/README.md` indexes the documentation tree. `docs/rag/` is the agent-facing knowledge-base corpus, auto-indexed at startup (`robofleet/services/optimal.py`, `AUTO_INDEX_DIRS`)  -  see `docs/rag/README.md` for the indexing mechanism and its actual reach under the ADK runtime (narrower than "indexed" implies  -  see that file before assuming a delivery agent can search it).
