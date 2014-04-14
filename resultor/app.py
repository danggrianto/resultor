from __future__ import unicode_literals

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def Index():
    return render_template('index.html')


@app.route("/pass")
def pass_test():
    return render_template('base_test.html')

if __name__ == '__main__':
    app.run()
