from flask import Flask, json
from flask import request
from flask import jsonify
from flask import abort
import os.path

app = Flask(__name__)


@app.route('/', methods=['GET'])
def mock_json():
    """
mock API to return a file at the localhost's path as Json
    :return: Json content from file
    """
    query_strings = request.args.to_dict()
    key = 'f'
    if key not in query_strings:
        abort(404)
    fname = query_strings[key]
    if not os.path.isfile(fname):
        abort(404)

    with open(fname) as json_data:
        excursions = json.load(json_data)
        return jsonify(excursions)
    return jsonify(query_strings)


if __name__ == '__main__':
    app.run()
