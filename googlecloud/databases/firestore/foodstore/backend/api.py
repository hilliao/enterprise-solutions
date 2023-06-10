import os
from flask import Flask
from flask_cors import CORS

from restapi import admin
from restapi import order

# Project ID is determined by the GCLOUD_PROJECT environment variable
app = Flask(__name__)
app.register_blueprint(admin.admin_api)
app.register_blueprint(order.order_api)
CORS(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
