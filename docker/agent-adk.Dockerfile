# ADK (Google ADK + Gemini) Agent Image
# =============================================================================
# Runs an agent as a Cloud Run Job execution: the orchestrator writes the tool
# manifest (flow_tools + do_tools + the composed system_prompt, inlined) to a
# local file, the CloudRunJobsProvider uploads it to GCS and sets
# ROBOFLEET_TOOL_MANIFEST_PATH to the gs:// URI, and this image's entrypoint
# (roboco.agent.adk_entry) fetches it, builds an ADK LlmAgent with the gateway
# tool-shim (roboco.agent.gateway_shim) + git/file FunctionTools
# (roboco.agent.git_tools), runs it to completion on Gemini, and POSTs usage
# to /api/v1/usage/report.
#
# No MCP servers (the shim calls the orchestrator HTTP directly), no Claude
# CLI, no Node.js: a pure Python ADK runtime. One image serves every role;
# role behaviour comes from the manifest's flow/do tool lists + system_prompt.
# =============================================================================

FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=4 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

# Deps first (cache stable across app-code changes), then source.
COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY robofleet /app/robofleet
RUN uv sync --frozen --no-dev

# Non-root user + git safe.directory (worktrees arrive owned by the
# orchestrator/Cloud Run, not the container user).
RUN useradd -m -s /bin/bash agent \
    && git config --global --add safe.directory '*'

USER agent

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "robofleet.agent.adk_entry"]