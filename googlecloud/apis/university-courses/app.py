import os

import psycopg2
from flask import Flask, jsonify, request
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DB_PARAM_HOST = os.environ["DB_HOST"]
DB_PARAM_PORT = "5432"
DB_PARAM_PASS = os.environ["DB_PASSWORD"]
DB_PARAM_USER = "postgres"
DB_PARAM_DATABASE = "courses"


@app.route('/add_student', methods=['POST'])
def add_student():
    """
    Create a student, including first and last name
    Example curl:
    curl -X POST -H "Content-Type: application/json" -d '{"first_name": "test", "last_name":"test"}' http://localhost:5002/add_student
[
  {
    "id": 5
  }
]
    """
    req = request.json
    first_name = req['first_name']
    last_name = req['last_name']

    # validate student name and check SQL injection
    if not all(char.isalpha() for char in first_name):
        return "First Name not valid", 400
    if not all(char.isalpha() for char in last_name):
        return "Last Name not valid", 400

    try:
        with psycopg2.connect(database=DB_PARAM_DATABASE,
                              user=DB_PARAM_USER, password=DB_PARAM_PASS,
                              host=DB_PARAM_HOST, port=DB_PARAM_PORT) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                insert_query = """INSERT INTO public.students(first_name, last_name) VALUES(%s,%s) RETURNING id"""
                cur.execute(insert_query, (first_name, last_name))
                rows = cur.fetchall()

    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    return rows


@app.route('/add_course', methods=['POST'])
def add_course():
    """
    Create courses, including the course name, course code, and description
    Example curl:
curl -X POST -H "Content-Type: application/json" -d '{"name": "test", "description":"test", "code": "56"}' http://localhost:5002/add_course
[
  {
    "id": 56
  }
]
(university-courses) hil@us-threadripper-24cpu-32g:~/git/enterprise-solutions/googlecloud/apis/university-courses$ curl -X POST -H "Content-Type: application/json" -d '{"name": "test", "description":"tes t", "code": "56"}' http://localhost:5002/add_course
Course description not valid(university-courses)
    """
    req = request.json
    name = req['name']
    id = req['code']
    description = req['description']

    # validate student name and check SQL injection
    if not all(char.isalpha() for char in name):
        return "Course Name not valid", 400
    if not all(char.isalpha() for char in description):
        return "Course description not valid", 400
    course_id = int(id)

    try:
        with psycopg2.connect(database=DB_PARAM_DATABASE,
                              user=DB_PARAM_USER, password=DB_PARAM_PASS,
                              host=DB_PARAM_HOST, port=DB_PARAM_PORT) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                insert_query = """INSERT INTO public.courses(id, name,description) VALUES(%s,%s,%s) RETURNING id"""
                cur.execute(insert_query, (course_id, name, description))
                rows = cur.fetchall()

    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    return rows


@app.route('/courses-taken')
def taken():
    """
    Show all students and which courses the students have taken
    Example output:
[
  {
    "courses_taken": null,
    "first_name": "Joe",
    "id": 1,
    "last_name": "Smoth"
  },
  {
    "courses_taken": null,
    "first_name": "Jane",
    "id": 2,
    "last_name": "Doe"
  },
  {
    "courses_taken": "456",
    "first_name": "David",
    "id": 3,
    "last_name": "Gardner"
  },
  {
    "courses_taken": "123,120",
    "first_name": "Amy",
    "id": 4,
    "last_name": "Lyall"
  }
]
    """
    conn = psycopg2.connect(database=DB_PARAM_DATABASE,
                            user=DB_PARAM_USER, password=DB_PARAM_PASS,
                            host=DB_PARAM_HOST, port=DB_PARAM_PORT)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = """
    SELECT * FROM PUBLIC.STUDENTS        
    """
    cur.execute(query)
    results = cur.fetchall()
    # close the cursor and connection
    cur.close()
    conn.close()

    return jsonify(results)


@app.route('/courses-not-taken')
def not_taken():
    """
    Show all students and which courses the students have not taken
    example output:
[
  {
    "courses_not_taken": [
      123,
      456,
      450,
      120
    ],
    "courses_taken": null,
    "first_name": "Joe",
    "id": 1,
    "last_name": "Smoth"
  },
  {
    "courses_not_taken": [
      123,
      456,
      450,
      120
    ],
    "courses_taken": null,
    "first_name": "Jane",
    "id": 2,
    "last_name": "Doe"
  },
  {
    "courses_not_taken": [
      123,
      450,
      120
    ],
    "courses_taken": "456",
    "first_name": "David",
    "id": 3,
    "last_name": "Gardner"
  },
  {
    "courses_not_taken": [
      456,
      450
    ],
    "courses_taken": "123,120",
    "first_name": "Amy",
    "id": 4,
    "last_name": "Lyall"
  }
]
    """
    conn = psycopg2.connect(database=DB_PARAM_DATABASE,
                            user=DB_PARAM_USER, password=DB_PARAM_PASS,
                            host=DB_PARAM_HOST, port=DB_PARAM_PORT)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = """
    SELECT * FROM PUBLIC.STUDENTS       
    """
    cur.execute(query)
    students_results = cur.fetchall()

    cur.execute("SELECT * FROM PUBLIC.COURSES")
    courses_results = cur.fetchall()

    # close the cursor and connection
    cur.close()
    conn.close()

    students_results = jsonify(students_results)
    courses_results = jsonify(courses_results)
    students_results_dict = students_results.json

    all_courses = [course['id'] for course in courses_results.json]
    for student in students_results_dict:
        courses_taken = courses_taken = student['courses_taken']
        if courses_taken:
            courses_taken = courses_taken.split(',')
            courses_not_taken = [c for c in all_courses if str(c) not in courses_taken]
            student['courses_not_taken'] = courses_not_taken
        else:
            student['courses_not_taken'] = all_courses

    return students_results_dict


if __name__ == '__main__':
    app.run(debug=True, port=5002)
