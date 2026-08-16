output "cloudsql_connection_name" {
  value       = google_sql_database_instance.roboco.connection_name
  description = "Cloud SQL connection name (project:region:instance)."
}

output "memorystore_host" {
  value       = google_redis_instance.roboco.host
  description = "Memorystore for Redis IP."
}

output "filestore_ip" {
  value       = google_filestore_instance.roboco.networks[0].ip_addresses[0]
  description = "Filestore NFS IP address."
}

output "filestore_share" {
  value       = google_filestore_instance.roboco.file_shares[0].name
  description = "Filestore share name mounted at /data/workspaces."
}

output "gcs_bucket" {
  value       = google_storage_bucket.roboco.name
  description = "GCS bucket name."
}

output "artifact_registry_repo" {
  value       = google_artifact_registry_repository.roboco.repository_id
  description = "Artifact Registry docker repository id."
}