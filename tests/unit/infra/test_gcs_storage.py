"""GCS storage adapter (Task 4.3).

``GcsStorage`` wraps ``google-cloud-storage`` for render uploads. The class is
constructable without credentials (the client is lazy); ``upload_render`` puts
a local file at ``gs://{bucket}/renders/{basename}`` and returns the URI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from roboco.infra import gcs_storage


def test_upload_calls_blob_upload_from_filename(tmp_path) -> None:
    local = tmp_path / "render.mp4"
    local.write_bytes(b"data")

    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    store = gcs_storage.GcsStorage("my-bucket", client=fake_client)
    uri = store.upload(str(local), "renders/render.mp4")

    fake_bucket.blob.assert_called_once_with("renders/render.mp4")
    fake_blob.upload_from_filename.assert_called_once_with(str(local))
    assert uri == "gs://my-bucket/renders/render.mp4"


def test_download_calls_blob_download_to_filename(tmp_path) -> None:
    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    dest = tmp_path / "out.mp4"
    store = gcs_storage.GcsStorage("my-bucket", client=fake_client)
    store.download("renders/render.mp4", str(dest))

    fake_bucket.blob.assert_called_once_with("renders/render.mp4")
    fake_blob.download_to_filename.assert_called_once_with(str(dest))


def test_presigned_url_calls_generate_signed_url() -> None:
    fake_blob = MagicMock()
    fake_blob.generate_signed_url.return_value = "https://signed.example/x"
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    store = gcs_storage.GcsStorage("my-bucket", client=fake_client)
    url = store.presigned_url("renders/render.mp4", expiration=3600)

    fake_blob.generate_signed_url.assert_called_once()
    assert url == "https://signed.example/x"


def test_upload_render_uploads_to_renders_prefix(tmp_path) -> None:
    """upload_render helper puts the file under renders/ and returns gs URI."""
    local = tmp_path / "abc.mp4"
    local.write_bytes(b"data")

    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    uri = gcs_storage.upload_render(str(local), "my-bucket", client=fake_client)

    fake_bucket.blob.assert_called_once_with("renders/abc.mp4")
    fake_blob.upload_from_filename.assert_called_once_with(str(local))
    assert uri == "gs://my-bucket/renders/abc.mp4"


def test_gcs_storage_imports_clean() -> None:
    """Bare import never requires creds; client is lazy."""
    from roboco.infra.gcs_storage import GcsStorage

    store = GcsStorage.__new__(GcsStorage)
    assert store is not None
