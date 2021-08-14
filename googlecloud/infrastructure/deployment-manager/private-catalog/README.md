# Private Catalog to create a blueprint
The private catalog deployment manager solution executes a cloud build step to git clone a cloud source repository
and to create a cloud build trigger that connects to the repository. 

## external dependency
the REPO_PATH needs to point to an existing path in git at googlecloud/infrastructure/blueprints/gke