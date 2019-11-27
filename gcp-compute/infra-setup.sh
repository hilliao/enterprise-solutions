# create cloud scheduler, pub/sub, cloud function

gcloud pubsub topics create delete-expired-gce
gcloud functions deploy delete_expired_gce --entry-point delete_expired --runtime python37 --trigger-topic delete-expired-gce