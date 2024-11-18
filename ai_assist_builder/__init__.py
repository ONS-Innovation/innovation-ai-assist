import os
import random
from http import HTTPStatus

import requests
from flask import Flask, json, redirect, render_template, request, session, url_for
from flask_misaka import Misaka

DEBUG = True
API_TIMER_SEC = 3

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Load the questions from the JSON file
with open("ai_assist_builder/content/tlfs_sic_soc.json") as file:
    questions_data = json.load(file)
    questions = questions_data["questions"]


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
    # When the user navigates to the home page, reset the session data
    if "current_question_index" in session:
        # Reset the current question index in the session
        session["current_question_index"] = 0

        # Clear the response data in the session
        if "response" in session:
            session.pop("response")

    return render_template("index.html")


# TODO - Breadcrumbs are not being rendered at the moment
@app.route("/previous_question")
def previous_question():
    # When the user navigates to the home page, reset the session data
    if "current_question_index" in session and session["current_question_index"] > 0:
        # Point to the prior question
        session["current_question_index"] -= 1
        return redirect(url_for("survey"))
    else:
        return render_template("index.html")


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


@app.route("/survey", methods=["GET", "POST"])
def survey():
    # Initialize the current question index in the session if it doesn't exist
    if "current_question_index" not in session:
        session["current_question_index"] = 0

    # Get the current question based on the index
    current_index = session["current_question_index"]
    current_question = questions[current_index]

    print("Current question index:", session["current_question_index"])
    print("Total number of questions:", len(questions))

    # if question_text contains PLACEHOLDER_TEXT, get the associated
    # placeholder_field associated with the question and replace the
    # PLACEHOLDER_TEXT string with the value of the specified field
    # help in session response
    if "PLACEHOLDER_TEXT" in current_question["question_text"]:
        # Copy the current question to a new dictionary
        current_question = current_question.copy()

        placeholder_field = current_question["placeholder_field"]

        if placeholder_field is not None:
            current_question["question_text"] = current_question["question_text"].replace(
                "PLACEHOLDER_TEXT", session["response"][placeholder_field]
            )
            print("Updated question text:", current_question["question_text"])
        else:
            print("No placeholder_field found for question:" + current_question["question_text"])

    return render_template("question_template.html", **current_question)


def update_session_and_redirect(key, value, route):
    session["response"][key] = request.form.get(value)
    session["current_question_index"] += 1
    session.modified = True
    return redirect(url_for(route))


@app.route("/save_response", methods=["POST"])
def save_response():

    # Define a dictionary to store responses
    if "response" not in session:
        print("No session data found")
        session["response"] = {}

    print(session["response"])

    actions = {
        "paid_job_question": lambda: update_session_and_redirect(
            "paid_job", "paid-job", "survey"
        ),
        "zero_hour_question": lambda: update_session_and_redirect(
            "zero_hour", "zero-hour-contract", "survey"
        ),
        "job_title_question": lambda: update_session_and_redirect(
            "job_title", "job-title", "survey"
        ),
        "job_description_question": lambda: update_session_and_redirect(
            "job_description",
            "job-description",
            "survey",
        ),
        "organisation_activity_question": lambda: update_session_and_redirect(
            "organisation_activity",
            "organisation-activity",
            "survey",
        ),
        "organisation_type_question": lambda: update_session_and_redirect(
            "organisation_type", "organisation-type", "survey"
        ),
        "longer_hours_question": lambda: update_session_and_redirect(
            "longer_hours", "longer-hours", "summary"
        ),
    }

    question = request.form.get("question_name")

    print("Question:", question)
    print("Actions:", actions[question])

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
