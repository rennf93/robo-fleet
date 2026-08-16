# =============================================================================
# Load balancer + Serverless VPC Access connector (Phase 5.5).
# APPENDS to the existing infra/*.tf; does not modify main.tf/variables.tf.
# Plain hyphens only, no em-dashes.
# =============================================================================
#
# X-Agent-Token nginx injection is DROPPED on GCP: ROBOCO_CLOUD_AUTH_ENABLED=true
# is the auth gate (the validator forbids BOTH nginx-static-token AND cloud auth
# at the same time). The nginx X-Agent-Token injection (ROBOCO_PANEL_AGENT_TOKEN)
# is NOT carried into any Cloud Run manifest or LB config. Cloud auth's cookie +
# JWT session is the sole human-auth path on GCP.
#
# The Serverless VPC Access connector is always created (the orchestrator and
# agent job manifests reference it by name to reach Memorystore on its private
# IP). The global HTTPS LB is optional: set lb_domain to a custom domain to
# provision it, or leave it empty to use the .run.app direct URLs directly
# (the documented hackathon-demo choice - no domain or SSL cert needed).

variable "lb_domain" {
  type        = string
  default     = ""
  description = "Custom domain for the global HTTPS LB. Empty = use .run.app direct URLs (no LB)."
}

# -----------------------------------------------------------------------------
# Serverless VPC Access connector.
# Lets Cloud Run services + jobs reach Memorystore (and Cloud SQL private IP)
# on the roboco-net VPC. The orchestrator + agent job manifests reference this
# connector by its name via the run.googleapis.com/vpc-access-connector
# annotation.
# -----------------------------------------------------------------------------
resource "google_vpc_access_connector" "roboco" {
  name          = "roboco-connector"
  region        = var.region
  network       = google_compute_network.roboco.name
  ip_cidr_range = "10.8.0.0/28"
  machine_type  = "e2-standard-4"
  min_instances = 2
  max_instances = 3
}

output "vpc_connector_name" {
  value       = google_vpc_access_connector.roboco.name
  description = "Serverless VPC Access connector name (referenced by Cloud Run services + jobs)."
}

# -----------------------------------------------------------------------------
# Global HTTPS Load Balancer (optional, conditional on var.lb_domain).
# Fronts the orchestrator + panel Cloud Run services with path-based routing:
#   /api/* and /ws/*  ->  orchestrator backend
#   everything else   ->  panel backend
# When lb_domain is empty the .run.app direct URLs are used instead (no LB,
# no SSL cert, no domain required). This is the hackathon-demo default.
# -----------------------------------------------------------------------------
resource "google_compute_global_address" "lb" {
  count   = var.lb_domain != "" ? 1 : 0
  name    = "roboco-lb-ip"
  project = var.project_id
}

resource "google_compute_managed_ssl_certificate" "lb" {
  count   = var.lb_domain != "" ? 1 : 0
  name    = "roboco-lb-cert"
  project = var.project_id
  managed {
    domains = [var.lb_domain]
  }
}

# Serverless NEGs for the two Cloud Run services.
resource "google_compute_region_network_endpoint_group" "orchestrator" {
  count                 = var.lb_domain != "" ? 1 : 0
  name                  = "roboco-orchestrator-neg"
  region                = var.region
  project               = var.project_id
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = "roboco-orchestrator"
  }
}

resource "google_compute_region_network_endpoint_group" "panel" {
  count                 = var.lb_domain != "" ? 1 : 0
  name                  = "roboco-panel-neg"
  region                = var.region
  project               = var.project_id
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = "roboco-panel"
  }
}

# Backend services (global, fronting the regional serverless NEGs).
resource "google_compute_backend_service" "orchestrator" {
  count     = var.lb_domain != "" ? 1 : 0
  name      = "roboco-orchestrator-backend"
  project   = var.project_id
  protocol  = "HTTPS"
  backend {
    group = google_compute_region_network_endpoint_group.orchestrator[0].id
  }
}

resource "google_compute_backend_service" "panel" {
  count     = var.lb_domain != "" ? 1 : 0
  name      = "roboco-panel-backend"
  project   = var.project_id
  protocol  = "HTTPS"
  backend {
    group = google_compute_region_network_endpoint_group.panel[0].id
  }
}

# URL map: /api/* and /ws/* -> orchestrator, everything else -> panel.
resource "google_compute_url_map" "roboco" {
  count           = var.lb_domain != "" ? 1 : 0
  name            = "roboco-url-map"
  project         = var.project_id
  default_service = google_compute_backend_service.panel[0].id
  host_rule {
    hosts        = [var.lb_domain]
    path_matcher = "main"
  }
  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.panel[0].id
    path_rule {
      paths   = ["/api/*", "/ws/*"]
      service = google_compute_backend_service.orchestrator[0].id
    }
  }
}

resource "google_compute_target_https_proxy" "roboco" {
  count             = var.lb_domain != "" ? 1 : 0
  name              = "roboco-https-proxy"
  project           = var.project_id
  url_map           = google_compute_url_map.roboco[0].id
  ssl_certificates  = [google_compute_managed_ssl_certificate.lb[0].id]
}

resource "google_compute_global_forwarding_rule" "https" {
  count    = var.lb_domain != "" ? 1 : 0
  name     = "roboco-https-fw"
  project  = var.project_id
  target   = google_compute_target_https_proxy.roboco[0].id
  port_range = "443"
  ip_address = google_compute_global_address.lb[0].address
}

output "lb_ip_address" {
  value       = var.lb_domain != "" ? google_compute_global_address.lb[0].address : ""
  description = "Global LB IPv4 address (empty when lb_domain is unset, .run.app direct URLs are used)."
}