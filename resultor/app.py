from __future__ import unicode_literals

from functools import wraps
import time

from flask import Flask, render_template, request, Response
from flask.ext.pymongo import PyMongo
from flask.ext.restful import Api, Resource


app = Flask(__name__)
# use mongodb on evo
# app.config['MONGO_HOST'] = '10.212.0.249'
# app.config['MONGO_DBNAME'] = 'resultor'
app.config['MONGO_URI'] =\
    'mongodb://aweber:aweber1100@oceanic.mongohq.com:10007/resultor'
mongo = PyMongo(app)
api = Api(app)


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == 'aweber' and password == 'aweber1100'


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@app.route("/", methods=['GET', 'POST'])
@requires_auth
def Index():
    results = mongo.db.info.find()
    sort = 'time'
    direction = 1
    if request.method == "POST":
        sort = request.form['sort']
        direction = request.form['direction']
    results = results.sort(sort, int(direction))
    return render_template(
        'index.html', results=results, sort=sort, direction=direction)


@app.route("/modules")
@requires_auth
def all_modules():
    modules = mongo.db.info.aggregate(
        [{'$group': {
            '_id': '$module',
            'status': {'$addToSet': '$status'},
        }}])['result']
    return render_template("modules.html", modules=modules)


@app.route("/<module>")
@requires_auth
def show_module(module):
    query = {'module': module}
    tests = mongo.db.info.find(query).sort('name', 1)
    return render_template(
        'module.html', module=module, tests=tests)


@app.route("/<module>/<name>", methods=['GET', 'POST'])
@requires_auth
def show_test(module, name):
    if request.method == "POST":
        flappy = 'on' in request.form.values()
        mongo.db.info.update(
            {'module': module, 'name': name}, {'$set': {'flappy': flappy}})
    query = {'name': name, 'module': module}
    info = mongo.db.info.find_one_or_404(query)
    results = mongo.db.results.find(query).sort('timestamp', -1)
    average = mongo.db.info.find_one(query)['average']
    return render_template(
        'base_test.html', info=info, results=results, avg=round(average, 2))


####
##
## REST
##
####

class Result(Resource):
    def put(self):
        results = request.get_json(force=True)
        for json in results:
            timestamp = int(round(time.time() * 1000))
            json['timestamp'] = timestamp
            mongo.db.results.insert(json)
            module = json['module']
            name = json['name']
            current_status = json['status']
            duration = json['duration']
            aggregation = [
                {'$match': {
                    'module': module, 'name': name, 'status': 'pass'}},
                {'$group': {
                    '_id': {'name': '$name', 'module': '$module'},
                    'average': {'$avg': "$duration"}}}]
            aggregate = mongo.db.results.aggregate(aggregation)
            result = aggregate['result']
            average = round(result[0]['average'], 2) if result else 0
            count = mongo.db.results.find(
                {'name': name, 'module': module}).count()
            fail_count = mongo.db.results.find(
                {'name': name, 'module': module, 'status': 'fail'}).count()
            try:
                flappy = mongo.db.info.find_one(
                    {'name': name, 'module': module})['flappy']
            except:
                flappy = False
            current_status = 'flappy' if flappy and (current_status == 'fail')\
                else current_status
            mongo.db.info.update(
                {'name': name, 'module': module},
                {'$set': {
                    'average': average,
                    'count': count,
                    'fail_count': fail_count,
                    'status': current_status,
                    'duration': duration,
                    'timestamp': timestamp
                }}, True)
        return {}


def short_string(long_string):
    if long_string.__len__() > 100:
        short = '...{0}'.format(long_string[-100:])
    else:
        short = long_string
    return short

app.jinja_env.globals.update(short_string=short_string)

api.add_resource(Result, '/api/result')


if __name__ == '__main__':
    app.run(debug=True)
