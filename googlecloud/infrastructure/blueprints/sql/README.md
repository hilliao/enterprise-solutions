# Google Cloud SQL blueprint
Create a cloud SQL instance from the blueprint in a [project namespace](https://cloud.google.com/anthos-config-management/docs/tutorials/project-namespace-blueprint#configure_a_project_namespace).
Follow the instructions in the link to create a blueprints GKE cluster namespace for the tenant project where the cloud
SQL instance will be created.

## Configure a project namespace
Modify setters.yaml in [the doc](https://cloud.google.com/anthos-config-management/docs/tutorials/project-namespace-blueprint#configure_a_project_namespace)
per setters.yaml-tenant-project-folder. Replace the `data:` section with the values.

0. projects-namespace: config-control is the GKE namespace to manage tenant project permissions
1. networking-namespace: tenant-demo-project is the project ID of the tenant project
2. management-project-id: prj-blueprints is the project ID of the blueprints GKE cluster
3. project-id: tenant-demo-project is the tenant project ID
4. management-namespace: config-control is the GKE namespace to manage project namespaces