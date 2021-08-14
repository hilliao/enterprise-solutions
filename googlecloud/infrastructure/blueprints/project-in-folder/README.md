# Google folder, project blueprint
This blueprint creates a folder and a project in it

## Set the values in setters.yaml:
- name is used for folder and project name
- project-id-in-folder which will append random characters
- parent-folder-id is the parent folder to create a folder under, requires quotes otherwise apply command will fail to parse as string
- random is to avoid existing project ID or that in pending deletion to fail project creation

## Create the following IAM role binding 
${FOLDER_ID} can be in a different organization. Bind the following IAM roles to
service-[PROJECT_NUMBER]@gcp-sa-yakima.iam.gserviceaccount.com:
- Folder Creator
- Folder Editor 
- Project Creator
- Project Deleter

Bind `Billing Account User` IAM role to service-[PROJECT_NUMBER]@gcp-sa-yakima.iam.gserviceaccount.com