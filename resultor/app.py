from __future__ import unicode_literals

import time

from flask import Flask, render_template, request
from flask.ext.pymongo import PyMongo
from flask.ext.restful import Api, Resource


app = Flask(__name__)
app.config['MONGO_DBNAME'] = 'resultor'
mongo = PyMongo(app)
api = Api(app)


@app.route("/")
def Index():
    return render_template('index.html')


@app.route("/modules")
def all_modules():
    modules = mongo.db.info.aggregate(
        [{'$group': {
            '_id': '$module',
            'status': {'$addToSet': '$status'}
        }}])['result']
    return render_template("modules.html", modules=modules)


@app.route("/<module>")
def show_module(module):
    query = {'module': module}
    tests = mongo.db.info.find(query).sort('name', 1)
    return render_template(
        'module.html', module=module, tests=tests)


@app.route("/<module>/<name>", methods=['GET', 'POST'])
def show_test(module, name):
    if request.method == "POST":
        flappy = 'on' in request.form.values()
        mongo.db.info.update(
            {'module': module, 'name': name}, {'$set': {'flappy': flappy}})
    query = {'name': name, 'module': module}
    info = mongo.db.info.find_one_or_404(query)
    results = mongo.db.results.find(query).sort('timestamp', -1)
    aggregation = [
        {'$match': {
            'module': module, 'name': name, 'status': 'pass'}},
        {'$group': {
            '_id': {'name': '$name', 'module': '$module'},
            'average': {'$avg': "$duration"}}}]
    average = mongo.db.results.aggregate(aggregation)['result'][0]['average']
    return render_template(
        'base_test.html', info=info, results=results, avg=round(average, 2))


####
##
## REST
##
####

class Result(Resource):
    def put(self):
        json = request.get_json(force=True)
        json['timestamp'] = int(round(time.time() * 1000))
        mongo.db.results.insert(json)
        module = json['module']
        name = json['name']
        aggregation = [
            {'$match': {
                'module': module, 'name': name, 'status': 'pass'}},
            {'$group': {
                '_id': {'name': '$name', 'module': '$module'},
                'average': {'$avg': "$duration"}}}]
        average = mongo.db.results.aggregate(
            aggregation)['result'][0]['average']
        count = mongo.db.results.find(
            {'name': name, 'module': module}).count()
        fail_count = mongo.db.results.find(
            {'name': name, 'module': module, 'status': 'fail'}).count()
        mongo.db.info.update(
            {'name': name, 'module': module},
            {'$set': {
                'average': average, 'count': count, 'fail_count': fail_count
            }}, True)
        return {}


api.add_resource(Result, '/api/result')


if __name__ == '__main__':
    app.run(debug=True)
