output "cloudsql_connection_name" {
  value       = google_sql_database_instance.robofleet.connection_name
  description = "Cloud SQL connection name (project:region:instance)."
}

output "cloudsql_private_ip" {
  value       = google_sql_database_instance.robofleet.private_ip_address
  description = "Cloud SQL private IP, reached over the VPC connector (TCP)."
}

output "memorystore_host" {
  value       = google_redis_instance.robofleet.host
  description = "Memorystore for Redis IP."
}

output "filestore_ip" {
  value       = google_filestore_instance.robofleet.networks[0].ip_addresses[0]
  description = "Filestore NFS IP address."
}

output "filestore_share" {
  value       = google_filestore_instance.robofleet.file_shares[0].name
  description = "Filestore share name mounted at /data/workspaces."
}

output "gcs_bucket" {
  value       = google_storage_bucket.robofleet.name
  description = "GCS bucket name."
}

output "artifact_registry_repo" {
  value       = google_artifact_registry_repository.robofleet.repository_id
  description = "Artifact Registry docker repository id."
}