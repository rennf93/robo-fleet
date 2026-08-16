#!/usr/bin/env bash
# Manual-run / debug entrypoint for the ADK agent image. The Dockerfile's
# ENTRYPOINT calls the python module directly; this wrapper exists only so an
# operator can `docker run ... /app/scripts/agent-adk-entrypoint.sh` with the
# same argv without remembering the module path.
exec python -m roboco.agent.adk_entry "$@"