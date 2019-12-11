# Create cloud scheduler, pub/sub, cloud function. The following roles are recommended to deploy and manage the solution
# TODO: gcloud command to create cloud scheduler job
gcloud pubsub topics create delete-expired-gce

# get the project number to form the compute engine default service account for cloud function to use
PROJECT=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT" --format="value(PROJECT_NUMBER)")
# if the production uses another service account for deleting instance, set --service-account to that service account
gcloud functions deploy delete-expired-gce --entry-point=main --runtime=python37 --trigger-topic=delete-expired-gce \
--service-account=$PROJECT_NUMBER-compute@developer.gserviceaccount.com --memory=128MB &