terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ---------------------------------------------------------
# Enabled Services
# ---------------------------------------------------------
resource "google_project_service" "blockchainnodeengine" {
  service            = "blockchainnodeengine.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudfunctions" {
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

# ---------------------------------------------------------
# Cloud SQL (PostgreSQL)
# ---------------------------------------------------------
resource "google_sql_database_instance" "main" {
  name             = "tinyhub-postgres"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled = true
    }
  }
}

resource "google_sql_database" "database" {
  name     = "tinyhub"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "user" {
  name     = "tinyhub_app"
  instance = google_sql_database_instance.main.name
  password = var.db_password
}

# ---------------------------------------------------------
# Firestore
# ---------------------------------------------------------
resource "google_firestore_database" "database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# ---------------------------------------------------------
# Cloud KMS
# ---------------------------------------------------------
resource "google_kms_key_ring" "keyring" {
  name     = "tinyhub-user-wallets"
  location = var.region
}

resource "google_kms_crypto_key" "wallet_key" {
  name     = "test-wallet-key"
  key_ring = google_kms_key_ring.keyring.id
  purpose  = "ENCRYPT_DECRYPT"
}

# ---------------------------------------------------------
# Arbitrum Node VM & Network
# ---------------------------------------------------------
resource "google_compute_firewall" "allow_arbitrum_p2p" {
  name    = "allow-arbitrum-p2p"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["30303"]
  }

  allow {
    protocol = "udp"
    ports    = ["30303"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["arbitrum-node"]
}

resource "google_compute_instance" "arbitrum_node" {
  name         = "arbitrum-sepolia-node"
  machine_type = "e2-standard-4"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 200
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = "default"
    access_config {
      // Ephemeral IP
    }
  }

  tags = ["arbitrum-node"]
}

# ---------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------
resource "google_secret_manager_secret" "deployer_key" {
  secret_id = "DEPLOYER_PRIVATE_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "deployer_key_version" {
  secret      = google_secret_manager_secret.deployer_key.id
  secret_data = var.deployer_private_key
}

resource "google_secret_manager_secret" "settler_key" {
  secret_id = "SETTLER_PRIVATE_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "settler_key_version" {
  secret      = google_secret_manager_secret.settler_key.id
  secret_data = var.settler_private_key
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "tinyhub-db-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url_version" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql://tinyhub_app:${var.db_password}@${google_sql_database_instance.main.public_ip_address}:5432/tinyhub"
}

# ---------------------------------------------------------
# Cloud Functions placeholders (Require source code zip in practice)
# ---------------------------------------------------------
# Note: In a full terraform setup, you'd zip the source code and upload to GCS.
# We define the framework for the functions you had deployed via scripts.

resource "google_storage_bucket" "functions_bucket" {
  name     = "${var.project_id}-functions-src"
  location = var.region
}

# (The actual function deployments would reference objects in this bucket.
#  They are omitted here for brevity as they require zipped source artifacts.)
