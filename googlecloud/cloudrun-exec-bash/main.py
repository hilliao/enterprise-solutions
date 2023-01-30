# Copyright 2021 GoogleCloud.fr. This software is provided as-is, without warranty
# or representation for any use or purpose. Your use of it is subject to your agreement with GoogleCloud.fr

import os
from flask import Flask, request
import subprocess

app = Flask(__name__)


@app.route("/")
def hello_world():
    exec_result = subprocess.run(["/bin/bash", "/app/test-ssh.sh"], capture_output=True, text=True)
    return "Executed bash script with stdout: " + exec_result.stdout


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
