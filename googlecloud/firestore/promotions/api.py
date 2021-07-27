#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/

import os
from flask import Flask
from flask_cors import CORS

from stor import query

app = Flask(__name__)
app.register_blueprint(query.query_api)
CORS(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
