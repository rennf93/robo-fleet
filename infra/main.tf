resource "google_compute_network" "robofleet" {
  name = "robofleet-net"
}

resource "google_sql_database_instance" "robofleet" {
  name             = var.cloudsql_instance_name
  database_version = "POSTGRES_16"
  region           = var.region
  settings {
    edition           = "ENTERPRISE"
    tier              = "db-custom-2-7680"
    disk_size         = 20
    availability_type = "REGIONAL"
    ip_configuration {
      ipv4_enabled       = false
      private_network    = google_compute_network.robofleet.id
      enable_private_path_for_google_cloud_services = true
    }
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

resource "google_sql_database" "robofleet" {
  name     = "robofleet"
  instance = google_sql_database_instance.robofleet.name
}

resource "google_sql_user" "robofleet" {
  name     = "robofleet"
  instance = google_sql_database_instance.robofleet.name
  password = var.db_password
}

resource "google_redis_instance" "robofleet" {
  name           = "robofleet-cache"
  region         = var.region
  tier           = "BASIC"
  memory_size_gb = 1
  redis_version  = "REDIS_7_0"
  # ponytail: no-auth is safe here, Redis is private-VPC only (not internet-reachable)
  auth_enabled   = false
  connect_mode   = "PRIVATE_SERVICE_ACCESS"
  authorized_network = google_compute_network.robofleet.id

  depends_on = [google_service_networking_connection.private_service_access]
}

resource "google_filestore_instance" "robofleet" {
  name     = "robofleet-workspaces"
  location = "${var.region}-a"
  tier     = "BASIC_HDD"
  file_shares {
    name        = "workspaces"
    capacity_gb = var.filestore_capacity_gb
  }
  networks {
    network = google_compute_network.robofleet.name
    modes   = ["MODE_IPV4"]
  }
}

resource "google_storage_bucket" "robofleet" {
  name                     = var.gcs_bucket
  location                 = var.region
  uniform_bucket_level_access = true
}

resource "google_artifact_registry_repository" "robofleet" {
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

resource "google_compute_global_address" "private_service_access" {
  name          = "robofleet-psa-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.robofleet.id
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = google_compute_network.robofleet.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}