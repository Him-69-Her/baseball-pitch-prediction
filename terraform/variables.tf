variable "project_id" {
  description = "The GCP Project ID"
  type        = string
  default     = "tiny-hub-network"
}

variable "region" {
  description = "The default GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The default GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "db_password" {
  description = "The password for the PostgreSQL database user"
  type        = string
  sensitive   = true
}

variable "deployer_private_key" {
  description = "The private key for deploying smart contracts"
  type        = string
  sensitive   = true
}

variable "settler_private_key" {
  description = "The private key for the batch settler"
  type        = string
  sensitive   = true
}
