module "bucket" {
  source = "git::https://github.com/terraform-google-modules/terraform-google-cloud-storage.git//modules/simple_bucket?ref=v4.0.0"

  name          = join("_", [var.project_id, "test-tmp-bucket"])
  project_id    = var.project_id
  location      = var.region
  storage_class = "STANDARD"
  iam_members = [{
    role   = "roles/objectViewer"
    member = "allUsers"
  }]
}
