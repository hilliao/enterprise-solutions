# Sample microservices
Data Engineering – Interview Project 

Summary: Design and develop an API for University Courses 

Create a docker container for the API and an associated docker compose file for deploying all necessary components, allowing it to run on Ubuntu.  Please utilize the programming language / database of your choice for this project. 
Ensure the API is RESTful and the API includes data validation.  Please add additional comments for functionality that you think should be added if time allowed. 


Key components:  

As a user of the API, I should be able to:  

* Create a student, including first and last name 
* Create courses, including the course name, course code, and description 
* Show all students and which courses the students have taken 
* Show all students and which courses the students have not taken 

Final Output should include:  
* Source Code uploaded to Codility. 
* Docker File 
* Docker Compose File 
* Ability to execute on Ubuntu 
* Readme file with instructions 

NOTE: Do not use Object-Relational Mapping (ORM) 

"Pre-requirement - You need to install docker in your local environment to test your solution"


# Configure the database
The database is PostgreSQL 15 running as a Google Cloud SQL instance. The database is `courses`. There are 2 tables:
students, courses

```sql
-- Database: courses

-- DROP DATABASE IF EXISTS courses;

CREATE DATABASE courses
    WITH
    OWNER = cloudsqlsuperuser
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF8'
    LC_CTYPE = 'en_US.UTF8'
    LOCALE_PROVIDER = 'libc'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1
    IS_TEMPLATE = False;
    
-- Table: public.courses

-- DROP TABLE IF EXISTS public.courses;

CREATE TABLE IF NOT EXISTS public.courses
(
    id integer NOT NULL DEFAULT nextval('courses_id_seq'::regclass),
    name character varying(255) COLLATE pg_catalog."default" NOT NULL,
    description character varying(10240) COLLATE pg_catalog."default",
    CONSTRAINT courses_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.courses
    OWNER to postgres;
    
-- Table: public.students

-- DROP TABLE IF EXISTS public.students;

CREATE TABLE IF NOT EXISTS public.students
(
    id integer NOT NULL DEFAULT nextval('students_id_seq'::regclass),
    first_name character varying(1024) COLLATE pg_catalog."default",
    last_name character varying(1024) COLLATE pg_catalog."default",
    courses_taken character varying(10240) COLLATE pg_catalog."default",
    CONSTRAINT students_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.students
    OWNER to postgres;
```
The rows in the 2 tables are in the .png files.

# Deployment
## Command to build the docker image:

`$ docker build -t dematic-interview:prod /path/to/folder` 

The image is tagged as `dematic-interview:prod`. Consider tagging it and push to Google cloud artifact registry.

## Command to run the container at port 5002 on localhost
The database password and IP need to be passed at runtime. The command below uses `XXXYYYZZZ` and `34.72.218.000`
as the placeholders:
`docker run --name dematic --env DB_PASSWORD=XXXYYYZZZ --env DB_HOST=34.72.218.000 -p 5002:5002 dematic-interview:prod`
Further deployment to Google Cloud run or GKE Autopilot in production is recommended.

# Unit testing
All methods have example outputs for developing unit tests. Review each method in app.py for details.