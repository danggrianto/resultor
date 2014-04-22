from __future__ import unicode_literals

import time

from flask import Flask, render_template, request
from flask.ext.pymongo import PyMongo
from flask.ext.restful import Api, Resource


app = Flask(__name__)
# use mongodb on evo
# app.config['MONGO_HOST'] = '10.212.0.249'
# app.config['MONGO_DBNAME'] = 'resultor'
app.config['MONGO_URI'] = 'mongodb://aweber:aweber1100@oceanic.mongohq.com:10007/resultor'
mongo = PyMongo(app)
api = Api(app)


@app.route("/")
def Index():
    groups = mongo.db.results.aggregate(
        [{'$group': {'_id': {'module': "$module", 'name': "$name"}}}])['result']
    results = []
    for group in groups:
        result = mongo.db.results.find(group['_id']).sort('timestamp', -1)[0]
        info = mongo.db.info.find_one(group['_id'])
        result['status'] = info['status']
        result['average'] = info['average']
        results.append(result)
    return render_template('index.html', results=results)


@app.route("/modules")
def all_modules():
    modules = mongo.db.info.aggregate(
        [{'$group': {
            '_id': '$module',
            'status': {'$addToSet': '$status'},
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
            json['timestamp'] = int(round(time.time() * 1000))
            mongo.db.results.insert(json)
            module = json['module']
            name = json['name']
            current_status = json['status']
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
                    'status': current_status
                }}, True)
        return {}


api.add_resource(Result, '/api/result')


if __name__ == '__main__':
    app.run(debug=True)
