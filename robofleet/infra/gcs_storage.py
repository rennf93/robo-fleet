"""GCS storage adapter (Task 4.3).

Wraps ``google-cloud-storage`` for render uploads to ``gs://{bucket}/renders/``.
The client is lazy: a bare ``from robofleet.infra import gcs_storage`` never
constructs a client and never needs GCP credentials. Callers pass an optional
``client`` for testing; in production the real ``storage.Client()`` is built on
first use inside ``_client``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class GcsStorage:
    """Thin wrapper over a GCS bucket for render upload/download/presign."""

    def __init__(self, bucket_name: str, *, client: Any = None) -> None:
        self._bucket_name = bucket_name
        self._client = client

    def _client_obj(self) -> Any:
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def _bucket(self) -> Any:
        return self._client_obj().bucket(self._bucket_name)

    def upload(self, local_path: str, key: str) -> str:
        """Upload a local file to ``gs://{bucket}/{key}`` and return the URI."""
        blob = self._bucket().blob(key)
        blob.upload_from_filename(local_path)
        return f"gs://{self._bucket_name}/{key}"

    def download(self, key: str, local_path: str) -> None:
        """Download ``gs://{bucket}/{key}`` to ``local_path``."""
        blob = self._bucket().blob(key)
        blob.download_to_filename(local_path)

    def presigned_url(self, key: str, *, expiration: int = 3600) -> str:
        """Return a signed URL for ``gs://{bucket}/{key}``.

        Valid for ``expiration`` seconds.
        """
        blob = self._bucket().blob(key)
        url: str = blob.generate_signed_url(version="v4", expiration=expiration)
        return url


def upload_render(local_path: str, bucket_name: str, *, client: Any = None) -> str:
    """Upload a render file to ``gs://{bucket}/renders/{basename}``; return the URI.

    Minimal wiring helper called from the render site only when
    ``settings.gcp_gcs_bucket`` is set. Mirrors the MinIO durable-copy
    posture: the caller keeps the local file as the source of truth and
    treats a failed PUT as non-fatal.
    """
    store = GcsStorage(bucket_name, client=client)
    key = f"renders/{Path(local_path).name}"
    return store.upload(local_path, key)
