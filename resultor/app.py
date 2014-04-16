from __future__ import unicode_literals

from flask import Flask, render_template, request
from flask.ext.pymongo import PyMongo

app = Flask(__name__)
app.config['MONGO_DBNAME'] = 'resultor'
mongo = PyMongo(app)


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

if __name__ == '__main__':
    app.run(debug=True)
