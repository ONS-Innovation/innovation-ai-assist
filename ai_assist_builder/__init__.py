import os
import random
from http import HTTPStatus

import requests
from flask import Flask, redirect, render_template, request, session, url_for
from flask_misaka import Misaka

DEBUG = True
API_TIMER_SEC = 3

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

Misaka(app)

app.jinja_env.add_extension("jinja2.ext.do")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["FREEZER_IGNORE_404_NOT_FOUND"] = True
app.config["FREEZER_DEFAULT_MIMETYPE"] = "text/html"
app.config["FREEZER_DESTINATION"] = "../build"
app.cache = {}


def print_session():
    if DEBUG:
        print("Session data:", session)
        print("Response data:", session.get("response"))


def print_api_response(random_id, character_name):
    if DEBUG:
        print("Random ID:", random_id)
        print("Character name:", character_name)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/question")
def question():
    return render_template("question.html")


@app.route("/radio_question")
def radio_question():
    return render_template("radio_question.html")


@app.route("/paid_job_question")
def paid_job_question():
    print_session()
    return render_template("paid_job_question.html")


@app.route("/zero_hour_question")
def zero_hour_question():
    print_session()
    return render_template("zero_hour_question.html")


@app.route("/job_title_question")
def job_title_question():
    print_session()
    return render_template("job_title_question.html")


@app.route("/job_description_question")
def job_description_question():
    print_session()
    response = session.get("response")
    return render_template(
        "job_description_question.html", job_title=response.get("job_title")
    )


@app.route("/organisation_activity_question")
def organisation_activity_question():
    print_session()
    return render_template("organisation_activity_question.html")


@app.route("/organisation_type_question")
def organisation_type_question():
    print_session()
    return render_template("organisation_type_question.html")


@app.route("/longer_hours_question")
def longer_hours_question():
    print_session()
    return render_template("longer_hours_question.html")


@app.route("/summary")
def summary():
    print_session()
    response = session.get("response")
    return render_template("summary.html", response=response)


@app.route("/thank_you")
def thank_you():
    print_session()
    return render_template("thank_you.html")


@app.route("/api_request", methods=["GET", "POST"])
def api_request():
    print_session()
    # make an api request
    try:
        response = requests.get(
            "https://api.sampleapis.com/simpsons/characters",
            timeout=API_TIMER_SEC,
        )

        if response.status_code != HTTPStatus.OK or not response.json():
            return redirect(url_for("error_page"))

        characters = response.json()

        random_id = random.randint(1, 500)  # noqa: S311

        # Index into the characters list
        if 0 <= random_id < len(characters):
            character_name = characters[random_id].get("name", "Unknown Character")
        else:
            return redirect(url_for("error_page"))

        print_api_response(random_id, character_name)
        return render_template("thank_you.html", character_name=character_name)

    except Exception as e:
        print("Error occurred:", e)
        return redirect(url_for("error_page"))


@app.route("/error")
def error_page():
    return "An error occurred. Please try again later."


def update_session_and_redirect(key, value, route):
    session["response"][key] = request.form.get(value)
    session.modified = True
    return redirect(url_for(route))


@app.route("/save_response", methods=["POST"])
def save_response():

    # Define a dictionary to store responses
    if "response" not in session:
        print("No session data found")
        session["response"] = {}

    actions = {
        "paid_job_question": lambda: update_session_and_redirect(
            "paid_job", "paid-job", "zero_hour_question"
        ),
        "zero_hour_question": lambda: update_session_and_redirect(
            "zero_hour", "zero-hour-contract", "job_title_question"
        ),
        "job_title_question": lambda: update_session_and_redirect(
            "job_title", "job-title", "job_description_question"
        ),
        "job_description_question": lambda: update_session_and_redirect(
            "job_description",
            "job-description",
            "organisation_activity_question",
        ),
        "organisation_activity_question": lambda: update_session_and_redirect(
            "organisation_activity",
            "organisation-activity",
            "organisation_type_question",
        ),
        "organisation_type_question": lambda: update_session_and_redirect(
            "organisation_type", "organisation-type", "longer_hours_question"
        ),
        "longer_hours_question": lambda: update_session_and_redirect(
            "longer_hours", "longer-hours", "summary"
        ),
    }

    question = request.form.get("question_id")

    if question in actions:
        return actions[question]()
    else:
        return "Invalid question ID", 400


@app.errorhandler(404)
@app.route("/page-not-found")
def page_not_found(e=None):
    return render_template("404.html"), 404 if e else 200


# Method provides a dictionary to the jinja templates, allowing variables
# inside the dictionary to be directly accessed within the template files
@app.context_processor
def set_variables():
    navigation = {"navigation": {}}
    return {"navigation": navigation}
