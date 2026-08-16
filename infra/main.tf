resource "google_compute_network" "roboco" {
  name = "roboco-net"
}

resource "google_sql_database_instance" "roboco" {
  name             = var.cloudsql_instance_name
  database_version = "POSTGRES_16"
  region           = var.region
  settings {
    tier              = "db-custom-2-7680"
    disk_size         = 20
    availability_type = "REGIONAL"
    backup_configuration {
      enabled = true
    }
    database_flags {
      name  = "cloudsql.logical_decoding"
      value = "off"
    }
  }
  deletion_protection = false
}

resource "google_sql_database" "roboco" {
  name     = "roboco"
  instance = google_sql_database_instance.roboco.name
}

resource "google_sql_user" "roboco" {
  name     = "roboco"
  instance = google_sql_database_instance.roboco.name
  password = var.db_password
}

resource "google_redis_instance" "roboco" {
  name           = "roboco-cache"
  region         = var.region
  tier           = "BASIC"
  memory_size_gb = 1
  redis_version  = "REDIS_7_X"
  auth_enabled   = true
}

resource "google_filestore_instance" "roboco" {
  name     = "roboco-workspaces"
  location = var.region
  tier     = "BASIC_HDD"
  file_shares {
    name        = "workspaces"
    capacity_gb = var.filestore_capacity_gb
  }
  networks {
    network = google_compute_network.roboco.name
    modes   = ["MODE_IPV4"]
  }
}

resource "google_storage_bucket" "roboco" {
  name                     = var.gcs_bucket
  location                 = var.region
  uniform_bucket_level_access = true
}

resource "google_artifact_registry_repository" "roboco" {
  location      = var.region
  repository_id = var.ar_repo
  format        = "DOCKER"
}

resource "google_secret_manager_secret" "keys" {
  for_each = toset([
    "fernet-key",
    "agent-auth-secret",
    "cloud-auth-secret",
    "gemini-api-key",
  ])
  secret_id = "${var.secret_prefix}-${each.key}"
  replication {
    auto {}
  }
}