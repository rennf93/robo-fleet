"""Demo cycle marker module for the RoboFleet E2E delivery-cycle validation.

Created by the E2E validation cycle against the GCP orchestrator. Proves a
leaf dev task moves pending -> claimed -> in_progress -> committed -> PR ->
QA -> documentation -> PM review -> CEO approval -> completed, end to end
through the gateway verbs on a real Cloud Run + Filestore + Cloud SQL stack
with no local Postgres, no local git, no local model.
"""

DEMO_CYCLE_VERSION: str = "1.0.0"
