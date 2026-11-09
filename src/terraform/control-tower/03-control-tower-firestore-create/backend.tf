# State lives in the Control Tower state bucket created by ControlTowerProjectCreate.
# The bucket name is passed by initialize.sh via TF_CLI_ARGS_init (-backend-config=bucket=...).
terraform {
  backend "gcs" {
    prefix = "control-tower/03-control-tower-firestore-create"
  }
}
