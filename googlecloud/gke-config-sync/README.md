# GKE config sync example of Syncing from multiple repositories

Sample repository code for [Guide to GKE with gke and Config sync](https://hilliao.medium.com/gke-with-istio-and-config-sync-37f0f1302d65)
requires the following steps for the root repository and the namespace repository. Create a cloud source repository
named gke-config as an example.

0. Create a `master` branch and an empty directory, `config-management` 
0. Copy files from `master-branch`/* recursively to `config-management`/
0. Create a namespace specific branch, `ns-hil` and an empty directory, `config-management`
0. Copy files from `namespace-branch`/* recursively to `config-management`/

## The resulting  repository's master branch should have the following structure:

```shell
.
└── config-management
    ├── cluster
    │   ├── role.yaml
    │   └── constraint-pod-res-limits.yaml
    ├── clusterregistry
    │   ├── clusterselector-gke-1.yaml
    │   ├── clusterselector-gke-2.yaml
    │   ├── gke-1.yaml
    │   └── gke-2.yaml
    ├── namespaces
    │   └── hil
    │       ├── namespace.yaml
    │       ├── repo-sync.yaml
    │       └── sync-rolebinding.yaml
    └── system
        └── repo.yaml
```        

## The resulting  repository's namespace branch should have the following structure:

```shell
.
└── config-management
    ├── namespaces
    │   └── hil
    │       └── sa-test.yaml
    └── system
        └── repo.yaml
```