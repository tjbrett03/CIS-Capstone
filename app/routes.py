from flask import Blueprint, render_template
from config.goals import GOALS
from config.audiences import AUDIENCES

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template("index.html", goals=GOALS, audiences=AUDIENCES)
