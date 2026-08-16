variable "project_id" {
  type        = string
  description = "GCP project id hosting the RoboCo stack."
}

variable "region" {
  type        = string
  description = "GCP region for all regional resources."
}

variable "cloudsql_instance_name" {
  type        = string
  default     = "robofleet-pg"
  description = "Cloud SQL instance name."
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Password for the robofleet Postgres user."
}

variable "gcs_bucket" {
  type        = string
  description = "Globally unique GCS bucket name for RoboCo state."
}

variable "ar_repo" {
  type        = string
  default     = "robo-fleet"
  description = "Artifact Registry docker repository id."
}

variable "secret_prefix" {
  type        = string
  default     = "robofleet"
  description = "Prefix applied to every Secret Manager secret id."
}

variable "filestore_capacity_gb" {
  type        = number
  default     = 1024
  description = "Filestore share size in GB (BASIC_HDD min is 1024)."
}