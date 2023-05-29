# Terraform policy control validation
Google Cloud has a new product called [Policy validation](https://cloud.google.com/docs/terraform/policy-validation) in Terraform.
This guide shows an example of how to integrate policy validation to your CI,CD pipelines.

## Initialize Terraform
Clone the repository to your local disk. Enter the directory and configure variables.tf with an editor like `nano`
The Terraform module creates a bucket in a project so there's not much to configure. If `Terraform` is NOT installed,
install it with the following 2 links:
* [Install Terraform](https://computingforgeeks.com/how-to-install-terraform-on-ubuntu/) on Ubuntu 22
* [Install Google Cloud CLI](https://cloud.google.com/sdk/docs/install) on Ubuntu then execute `sudo apt-get install google-cloud-sdk-terraform-tools`
```commandline
git clone https://github.com/hilliao/enterprise-solutions.git

# set default = "[Missing Project ID]"
nano enterprise-solutions/googlecloud/terraform/examples/simple_bucket/variables.tf

cd enterprise-solutions/googlecloud/terraform/examples/simple_bucket
terraform init
```

## Generate Terraform plan output file in JSON format
Refer to complete commands at [Policy validation](https://cloud.google.com/docs/terraform/policy-validation/quickstart). 
Make sure you have configured the credentials for `gcloud auth list` and
[Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) if you
are using a service account. To use a user account, refer to the command in the error message:
> Error: Attempted to load application default credentials since neither `credentials` nor `access_token` was set in the provider block.  No credentials loaded. To use your gcloud credentials, run 'gcloud auth application-default login'

Execute the commands to generate the `terraform plan` output file in JSON format.
```commandline
terraform plan -out=create_bucket.tfplan && \
terraform show -json ./create_bucket.tfplan > ./create_bucket.json
```
Verify `create_bucket.json` is generated.
## Clone the policy library at a different directory
The policy library contains policy constraint templates and constraints. I'm using 2 constraints.

```commandline
cd ~/ && \
git clone https://github.com/GoogleCloudPlatform/policy-library.git && \
cd policy-library && \
cp samples/storage_bucket_retention.yaml policies/constraints/ && \
cp samples/iam_deny_public.yaml policies/constraints
```

## Execute the vet command to check policy constraint violation

```commandline
gcloud beta terraform vet $HOME/enterprise-solutions/googlecloud/terraform/examples/simple_bucket/create_bucket.json \
  --policy-library=. --format=json | tee vet-violations.json
```

Observe the command output for the violated constraints
```json
[
  {
    "constraint": "GCPStorageBucketRetentionConstraintV1.storage_bucket_minimum_maximum_retention",
    "constraint_config": {
      "api_version": "constraints.gatekeeper.sh/v1alpha1",
      "kind": "GCPStorageBucketRetentionConstraintV1",
      "metadata": {
        "annotations": {
          "validation.gcp.forsetisecurity.org/originalName": "storage_bucket_minimum_maximum_retention",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/storage_bucket_retention.yaml"
        },
        "name": "storage-bucket-minimum-maximum-retention"
      },
      "spec": {
        "match": {
          "ancestries": [
            "organizations/**"
          ]
        },
        "parameters": {
          "exemptions": [],
          "maximum_retention_days": 30,
          "minimum_retention_days": 10
        },
        "severity": "high"
      }
    },
    "message": "Storage bucket //storage.googleapis.com/$PROJECT_ID_test-tmp-bucket has a retention policy violation: Lifecycle delete action does not exist when maximum_retention_days is defined",
    "metadata": {
      "ancestry_path": "organizations/996035508195/folders/743293467805/projects/$PROJECT_ID",
      "constraint": {
        "annotations": {
          "validation.gcp.forsetisecurity.org/originalName": "storage_bucket_minimum_maximum_retention",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/storage_bucket_retention.yaml"
        },
        "labels": {},
        "parameters": {
          "exemptions": [],
          "maximum_retention_days": 30,
          "minimum_retention_days": 10
        }
      },
      "details": {
        "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
        "violation_type": [
          "Lifecycle delete action does not exist when maximum_retention_days is defined"
        ]
      }
    },
    "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
    "severity": "high"
  },
  {
    "constraint": "GCPIAMAllowedBindingsConstraintV3.deny_allusers",
    "constraint_config": {
      "api_version": "constraints.gatekeeper.sh/v1alpha1",
      "kind": "GCPIAMAllowedBindingsConstraintV3",
      "metadata": {
        "annotations": {
          "bundles.validator.forsetisecurity.org/healthcare-baseline-v1": "security",
          "bundles.validator.forsetisecurity.org/scorecard-v1": "security",
          "description": "Prevent public users from having access to resources via IAM",
          "validation.gcp.forsetisecurity.org/originalName": "deny_allusers",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/iam_deny_public.yaml"
        },
        "name": "deny-allusers"
      },
      "spec": {
        "match": {
          "ancestries": [
            "organizations/**"
          ],
          "excludedAncestries": []
        },
        "parameters": {
          "members": [
            "allUsers",
            "allAuthenticatedUsers"
          ],
          "mode": "denylist",
          "role": "roles/*"
        },
        "severity": "high"
      }
    },
    "message": "IAM policy for //storage.googleapis.com/$PROJECT_ID_test-tmp-bucket grants roles/objectViewer to allUsers",
    "metadata": {
      "ancestry_path": "organizations/996035508195/folders/743293467805/projects/$PROJECT_ID",
      "constraint": {
        "annotations": {
          "bundles.validator.forsetisecurity.org/healthcare-baseline-v1": "security",
          "bundles.validator.forsetisecurity.org/scorecard-v1": "security",
          "description": "Prevent public users from having access to resources via IAM",
          "validation.gcp.forsetisecurity.org/originalName": "deny_allusers",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/iam_deny_public.yaml"
        },
        "labels": {},
        "parameters": {
          "members": [
            "allUsers",
            "allAuthenticatedUsers"
          ],
          "mode": "denylist",
          "role": "roles/*"
        }
      },
      "details": {
        "member": "allUsers",
        "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
        "role": "roles/objectViewer"
      }
    },
    "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
    "severity": "high"
  },
  {
    "constraint": "GCPStorageBucketRetentionConstraintV1.storage_bucket_minimum_maximum_retention",
    "constraint_config": {
      "api_version": "constraints.gatekeeper.sh/v1alpha1",
      "kind": "GCPStorageBucketRetentionConstraintV1",
      "metadata": {
        "annotations": {
          "validation.gcp.forsetisecurity.org/originalName": "storage_bucket_minimum_maximum_retention",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/storage_bucket_retention.yaml"
        },
        "name": "storage-bucket-minimum-maximum-retention"
      },
      "spec": {
        "match": {
          "ancestries": [
            "organizations/**"
          ]
        },
        "parameters": {
          "exemptions": [],
          "maximum_retention_days": 30,
          "minimum_retention_days": 10
        },
        "severity": "high"
      }
    },
    "message": "Storage bucket //storage.googleapis.com/$PROJECT_ID_test-tmp-bucket has a retention policy violation: Lifecycle delete action does not exist when maximum_retention_days is defined",
    "metadata": {
      "ancestry_path": "organizations/996035508195/folders/743293467805/projects/$PROJECT_ID",
      "constraint": {
        "annotations": {
          "validation.gcp.forsetisecurity.org/originalName": "storage_bucket_minimum_maximum_retention",
          "validation.gcp.forsetisecurity.org/yamlpath": "policies/constraints/storage_bucket_retention.yaml"
        },
        "labels": {},
        "parameters": {
          "exemptions": [],
          "maximum_retention_days": 30,
          "minimum_retention_days": 10
        }
      },
      "details": {
        "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
        "violation_type": [
          "Lifecycle delete action does not exist when maximum_retention_days is defined"
        ]
      }
    },
    "resource": "//storage.googleapis.com/$PROJECT_ID_test-tmp-bucket",
    "severity": "high"
  }
]
```
If you want to make it look scary in RED, you can do the following trick:
```commandline
RED='\033[0;31m'
NC='\033[0m' # No Color
VET_ERROR=`cat vet-violations.json`
printf "Policy validation error: ${RED} $VET_ERROR ${NC}\n"
```
