"""Infrastructure adapters for the GCP port (robo-fleet).

Each module is a guarded branch: when the corresponding ``gcp_*`` setting is
empty the local-dev path is byte-for-byte intact. Google clients are
lazy-imported inside methods so a bare ``from roboco.infra import ...`` never
requires GCP credentials at load time.
"""
