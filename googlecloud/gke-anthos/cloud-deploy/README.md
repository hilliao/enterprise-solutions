# Example of using cloud deploy to promote releases from dev to non-prod
```
gcloud beta deploy apply --file clouddeploy.yaml \
--region=us-central1 --project=gke-project

gcloud beta deploy releases create hil-testns-nginx-0 \
  --project=gke-project \
  --region=us-central1 \
  --delivery-pipeline=hil-deploy \
  --images=image-gcloud=gcr.io/google.com/cloudsdktool/cloud-sdk:latest,image-nginx=nginx
```