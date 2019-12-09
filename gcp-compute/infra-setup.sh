# Create cloud scheduler, pub/sub, cloud function. The following roles are recommended to deploy and manage the solution
# Cloud Functions Admin
# Cloud Scheduler Admin
# Compute Instance Admin (beta)
# Service Account User
# Pub/Sub Admin
# TODO: gcloud command to create cloud scheduler job
gcloud pubsub topics create delete-expired-gce

PROJECT=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT" --format="value(PROJECT_NUMBER)")
gcloud functions deploy delete-expired-gce --entry-point=main --runtime=python37 --trigger-topic=delete-expired-gce \
--service-account=$PROJECT_NUMBER-compute@developer.gserviceaccount.com --memory=128MB &