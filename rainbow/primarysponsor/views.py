from flask import Flask, render_template
from flask import request
import base64
import flask
import os
import sys
import json

app = Flask(__name__)


@app.route('/')
def home():
    debug_info = {
        'flask_version': flask.__version__,
        'uname': os.uname(),
        'python': sys.version
    }

    if 'MODULE_NAME' in os.environ:
        debug_info['MODULE_NAME'] = os.environ['MODULE_NAME']

    return debug_info


@app.route('/tickets/<ceremony>')
def template(ceremony):
    """
    return the ticket with watermark on the jpg file in static/
    TODO: error handling in query strings, path argument.

    query strings:
        registration token is the base64 UTF-8 encoded string to be decoded and overlay on the image. encode manually at https://www.base64encode.org/
        font pixel for the overlaid text on the image
    :param ceremony: MM-DD-YYYY -> static/MM-DD-YYYY.jpg
    :return: html template to render the primary sponsor ticket
    """
    token = request.args.get('reg-token')
    px = request.args.get('overlay_font_px')
    token_bytes = base64.b64decode(token)
    text = token_bytes.decode("utf-8")
    json_text = json.loads(text)

    return render_template('image-text.html',
                           image=ceremony,
                           first_name=json_text['first_name'],
                           last_name=json_text['last_name'],
                           phone=json_text['phone'],
                           seat=json_text['seat'],
                           overlay_font_px=px)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
