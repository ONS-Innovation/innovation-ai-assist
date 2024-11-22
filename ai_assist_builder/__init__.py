import os
import random
from http import HTTPStatus

import requests
from flask import (
    Flask,
    json,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_misaka import Misaka

from ai_assist_builder.models.question import Question

DEBUG = True
API_TIMER_SEC = 3
FOLLOW_UP_TYPE = "select"

number_to_word = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six"
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Load the questions from the JSON file
with open("ai_assist_builder/content/survey_definition.json") as file:
    survey_data = json.load(file)
    questions = survey_data["questions"]
    ai_assist = survey_data["ai_assist"]


# Initialise user survey data
# TODO - make a utility function
user_survey = {
    "survey": {"user": "", "questions": [], "time_start": None, "time_end": None}
}

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
        print("Survey data:", session.get("survey"))


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

        if "survey" in session:
            # Reinitialise the survey data
            session["survey"] = {
                "survey": {
                    "user": "",
                    "questions": [],
                    "time_start": None,
                    "time_end": None,
                }
            }

        session.modified = True

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


# Generic route to handle survey questions
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
            current_question["question_text"] = current_question[
                "question_text"
            ].replace("PLACEHOLDER_TEXT", session["response"][placeholder_field])
            print("Updated question text:", current_question["question_text"])
        else:
            print(
                "No placeholder_field found for question:"
                + current_question["question_text"]
            )

    return render_template("question_template.html", **current_question)


# A generic route that handles survey interactions (e.g call to AI)
# TODO - currently uses a mock endpoint for testing
@app.route("/survey_assist", methods=["GET", "POST"])
def survey_assist():
    question_type = FOLLOW_UP_TYPE

    base_url = "https://a3ab54bb-ec4c-413b-a406-fd4ee2434637.mock.pstmn.io/get"
    api_url = f"{base_url}?type={question_type}"

    try:
        # Send a request to the mocked API
        response = requests.get(api_url, timeout=API_TIMER_SEC)
        response_data = response.json()  # Convert the response to JSON

        # Get data from the response
        args = response_data.get("args", {})

        # TODO - handle the response data from AI
        # responses = args.get("responses", [])
        # categorisation = args.get("categorisation", {})

        follow_up = args.get("follow_up", {})

        print("Follow-up data:", follow_up)

        question_data = follow_up["questions"].pop(0)

        # The response is mapped into a question object
        # which is then added to the dynamic survey data
        # TODO - make a function to handle this
        mapped_question = Question(
            question_id=question_data["follow_up_id"],
            question_name=question_data["question_name"],
            question_title=question_data[
                "question_name"
            ],
            question_text=question_data["question_text"],
            response_type=question_data["response_type"],
            response_options=(
                [
                    {
                        "id": f"{option}-id",
                        "label": {"text": option},
                        "value": option,
                    }
                    for option in question_data["response_options"]
                ]
                if question_data["response_type"] == "select"
                else []
            ),
        )

        mapped_question_data = mapped_question.to_dict()

        user_survey = session.get("survey", {})
        response_name = (
            mapped_question_data.get("question_name")
            .replace("ai-assist-", "", 1)
            .replace("_", "-")
        )

        # Add "resp-" prefix to the response name
        response_name = f"resp-{response_name}"
        print("Response name:", response_name)

        # Add the question to the survey data
        user_survey["survey"]["questions"].append(
            {
                "question_id": mapped_question_data.get("question_id"),
                "question_text": mapped_question_data.get("question_text"),
                "response_type": mapped_question_data.get("response_type"),
                "response_options": mapped_question_data.get("response_options"),
                "response": None,  # added after user input
                "response_name": response_name,
            }
        )
        session.modified = True

        print("Survey Assist:" + str(user_survey["survey"]["questions"]))

        return render_template("question_template.html", **mapped_question.to_dict())
    except Exception as e:
        # Handle errors and return an appropriate message
        return jsonify({"error": str(e)}), 500


# Route called after each question (or interaction) to save response to session data.
# The response is saved to the session dictionary and the user is redirected to the
# next question or interaction.
# TODO - The actions dictionary is currently hardcoded for survey questions, this
# needs to be updated to be more dynamic.  There is also cruft in the variables passed
# to the update_session_and_redirect function.
@app.route("/save_response", methods=["POST"])
def save_response():

    # Define a dictionary to store responses
    if "response" not in session:
        print("Response session data NOT found")
        session["response"] = {}

    if "survey" not in session:
        print("Survey session data NOT found")
        session["survey"] = user_survey

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
        "follow_up_question": lambda: followup_redirect(),
    }

    question = request.form.get("question_name")
    print("Question:", question)
    if question.startswith("ai_assist"):
        question = "follow_up_question"
        # get survey data
        survey_data = session.get("survey")
        # get questions
        questions = survey_data["survey"]["questions"]

        print("SR SD:", survey_data)
        print("Length of questions:", len(questions))
        # get the last question
        last_question = questions[-1]
        # update the response
        print("Last question:", last_question)
        print("Response name:", last_question["response_name"])
        print("Form data:", request.form)
        last_question["response"] = request.form.get(last_question["response_name"])

        print("Last question:", last_question)

    if question in actions:
        print("Actions:", actions[question])
        return actions[question]()
    else:
        return "Invalid question ID", 400


# Route to make an API request (used for testing)
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
            return render_template("thank_you.html", character_name="API ERROR")
            # TODO return redirect(url_for("error_page"))

        characters = response.json()

        random_id = random.randint(1, 500)  # noqa: S311

        # Index into the characters list
        if 0 <= random_id < len(characters):
            character_name = characters[random_id].get("name", "Unknown Character")
        else:
            return render_template("thank_you.html", character_name="API ERROR")
            # TODO return redirect(url_for("error_page"))

        print_api_response(random_id, character_name)
        return render_template("thank_you.html", character_name=character_name)

    except Exception as e:
        print("Error occurred:", e)
        return render_template("thank_you.html", character_name="API ERROR")
        # TODO return redirect(url_for("error_page"))


# The survey route takes summarises the data that has been
# entered by user, using the session data held in the survey
# dictionary. The data is then displayed in a summary template
@app.route("/summary")
def summary():
    print_session()
    survey_data = session.get("survey")
    survey_questions = survey_data["survey"]["questions"]
    print("Survey questions:", survey_questions)
    return render_template("summary_template.html", questions=survey_questions)


# Rendered at the end of the survey
@app.route("/survey_assist_consent")
def survey_assist_consent():
    print("AI Assist consent "+str(ai_assist))

    if "PLACEHOLDER_FOLLOWUP" in ai_assist["consent"]["question_text"]:
        # Get the maximum followup
        max_followup = ai_assist["consent"]["max_followup"]

        if max_followup == 1:
            followup_text = "one additional question"
        else:
            # convert numeric to string
            number_word = number_to_word.get(max_followup, "unknown")

            followup_text = f"a maximum of {number_word} additional questions"

        # Replace PLACEHOLDER_FOLLOWUP wit the content of the placeholder field
        ai_assist["consent"]["question_text"] = ai_assist["consent"]["question_text"].replace(
            "PLACEHOLDER_FOLLOWUP", followup_text)

    if "PLACEHOLDER_REASON" in ai_assist["consent"]["question_text"]:
        # Replace PLACEHOLDER_REASON wit the content of the placeholder field
        ai_assist["consent"]["question_text"] = ai_assist["consent"]["question_text"].replace(
            "PLACEHOLDER_REASON", ai_assist["consent"]["placeholder_reason"])

    print("AI Assist consent question text:", ai_assist["consent"]["question_text"])
    return render_template("survey_assist_consent.html",
                           question_text=ai_assist["consent"]["question_text"],
                           justification_text=ai_assist["consent"]["justification_text"])


# Rendered at the end of the survey
@app.route("/thank_you")
def thank_you():
    print_session()
    return render_template("thank_you.html")


# Route to handle errors
@app.route("/error")
def error_page():
    return "An error occurred. Please try again later."


# Check if the current question has an associated follow-up that needs to be
# displayed to the user (this is typically a fllow up question from AI)
# TODO - This is currently only checking the first interaction, need to search
# for the current question in the interactions list.
def followup_redirect():
    current_question = questions[session["current_question_index"]]
    print("followup current_question:", current_question.get("question_id"))

    interactions = ai_assist.get("interactions")
    # Check if the current question has a follow-up question
    if len(interactions) > 0 and current_question.get("question_id") == interactions[
        0
    ].get("after_question_id"):
        print("FOLLOW UP - FOUND ")

        # Save the response to the session
        survey_data = session.get("survey")
        # get questions
        survey_questions = survey_data["survey"]["questions"]
        # get the last question
        last_question = survey_questions[-1]

        # update the response
        session["response"][last_question["response_name"]] = request.form.get(
            last_question["response_name"]
        )

        # increment the current question index
        session["current_question_index"] += 1
        session.modified = True
        return redirect(url_for("survey"))


# Handles the redirect after a question has been answered.
# For interactions this will be to the survey_assist route
# For regular questions this will be to the survey route
def update_session_and_redirect(key, value, route):
    session["response"][key] = request.form.get(value)

    print("Update session and redirect session survey data:", session.get("survey"))

    # Retrieve the survey data from the session
    user_survey = session.get("survey")

    if not user_survey:
        # Reinitialise survey in session if not present
        session["survey"] = {
            "user": "",
            "questions": [],
            "time_start": None,
            "time_end": None,
        }
        user_survey = session["survey"]
        print("User survey data:", user_survey)

    # Get the current question and take a copy so
    # that the original question data is not modified
    current_question = questions[session["current_question_index"]]
    current_question = current_question.copy()

    placeholder_field = current_question["placeholder_field"]

    if "response" in session and placeholder_field in session["response"]:
        current_question["question_text"] = current_question["question_text"].replace(
            "PLACEHOLDER_TEXT", session["response"][placeholder_field]
        )
        print("Updated question text:", current_question["question_text"])

    # Append the question and response to the list of questions
    user_survey["survey"]["questions"].append(
        {
            "question_id": current_question.get("question_id"),
            "question_text": current_question.get("question_text"),
            "response_type": current_question.get("response_type"),
            "response_options": current_question.get("response_options"),
            "response_name": current_question.get("response_name"),
            "response": request.form.get(value),
        }
    )

    if ai_assist.get("enabled", True):
        session.modified = True
        interactions = ai_assist.get("interactions")
        if len(interactions) > 0:
            print("Interactions:", interactions[0])
            print("current_question:", current_question.get("question_id"))
            print("interaction id:", interactions[0].get("after_question_id"))

            if current_question.get("question_id") == interactions[0].get(
                "after_question_id"
            ):
                print("AI Assist interaction detected - REDIRECTING")
                return redirect(url_for("survey_assist"))

    session["current_question_index"] += 1
    session.modified = True
    return redirect(url_for(route))


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
