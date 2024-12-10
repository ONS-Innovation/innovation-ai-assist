from datetime import datetime, timezone
import os
import random
import copy
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

from ai_assist_builder.models.api_map import map_api_response_to_internal
from ai_assist_builder.models.question import Question
from ai_assist_builder.utils.template_utils import render_classification_results, datetime_to_string
from ai_assist_builder.utils.classification_utils import get_questions_by_classification, filter_classification_responses

DEBUG = True
API_TIMER_SEC = 15
FOLLOW_UP_TYPE = "both"  # select or text or both
USER_ID = "steve.gibbard"
SURVEY_NAME = "TLFS PoC"

number_to_word = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Load the questions from the JSON file
with open("ai_assist_builder/content/condensed_tlfs_sic_soc.json") as file:
    survey_data = json.load(file)
    questions = survey_data["questions"]
    ai_assist = survey_data["ai_assist"]


# Initialise user survey data
# TODO - make a utility function
user_survey = {
    "survey": {"user": "",
               "questions": [],
               "time_start": None,
               "time_end": None,
               "survey_assist_time_start": None,
               "survey_assist_time_end": None}
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

        print("Index - Initialise survey data")
        # TODO - is this needed?
        # Reinitialise the survey data
        session["survey"] = {
            "survey": {
                "user": "",
                "questions": [],
                "time_start": None,
                "time_end": None,
                "survey_assist_time_start": None,
                "survey_assist_time_end": None,
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

        session.modified = True

    # Get the current question based on the index
    current_index = session["current_question_index"]
    current_question = questions[current_index]

    # print("Current question index:", session["current_question_index"])
    # print("Total number of questions:", len(questions))

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
            # print("Updated question text:", current_question["question_text"])
        #else:
            # print(
            #    "No placeholder_field found for question:"
            #    + current_question["question_text"]
            #)

    return render_template("question_template.html", **current_question)


def get_classification(llm, type, input_data):

    api_url = "http://127.0.0.1:5000/survey-assist/classify"
    body = {
        "llm": llm,
        "type": type,
        "job_title": input_data[0]["response"],
        "job_description": input_data[1]["response"],
        "org_description": input_data[2]["response"],
    }

    try:
        # Send a request to the Survey Assist API
        response = requests.post(api_url, json=body, timeout=API_TIMER_SEC)
        response_data = response.json()

        return response_data
    except Exception as e:
        print("Error occurred getting classification:", e)
        # Handle errors and return an appropriate message
        return jsonify({"error": str(e)}), 500


# A generic route that handles survey interactions (e.g call to AI)
# TODO - currently uses a mock endpoint for testing
@app.route("/survey_assist", methods=["GET", "POST"])
def survey_assist():

    llm = "gemini"  # gemini or chat-gpt
    type = "sic"  # sic or soc

    # Find the question about job_title
    user_response = session.get("response")

    api_url = "http://127.0.0.1:5000/survey-assist/classify"
    body = {
        "llm": llm,
        "type": type,
        "job_title": user_response.get("job_title"),
        "job_description": user_response.get("job_description"),
        "org_description": user_response.get("organisation_activity"),
    }

    try:
        # Send a request to the Survey Assist API
        response = requests.post(api_url, json=body, timeout=API_TIMER_SEC)
        response_data = response.json()

        # print("Response data:", response_data)

        api_response = map_api_response_to_internal(response_data)

        # print("AI Followup Questions:", api_response)
        followup_questions = api_response.get("follow_up", {}).get("questions", [])

        # print("Internal Mapped Followup Questions:", followup_questions)

        # If at least one question is available, loop through the questions
        # and print the question text
        if followup_questions:
            # Store the internal survey assist response in the session
            session["sa_response"] = api_response

            # Add the follow-up questions to the session data
            # first check if the follow-up questions are already
            # in the session data
            if "follow_up" not in session:
                session["follow_up"] = []

            session["follow_up"].extend(followup_questions)
            session.modified = True

            # for question in session["follow_up"]:
                # print("SESSION - AI Followup Question Data:", question)

        if FOLLOW_UP_TYPE in ["text", "both"]:
            followup = session.get("follow_up", {})
            question_data = followup.pop(0)
            question_text = question_data.get("question_text", "")
        elif FOLLOW_UP_TYPE == "select":
            followup = session.get("follow_up", {})
            question_data = followup.pop(-1)
            question_text = question_data.get("question_text", "")

        # for question in session["follow_up"]:
            # print("SESSION AFTER - AI Followup Question Data:", question)

        # The response is mapped into a question object
        # which is then added to the dynamic survey data
        # TODO - make a function to handle this
        mapped_question = Question(
            question_id=question_data["follow_up_id"],
            question_name=question_data["question_name"],
            question_title=question_data["question_name"],
            question_text=question_text,
            question_description="This question is generated by Survey Assist",
            response_type=question_data["response_type"],
            response_options=(
                [
                    {
                        "id": f"{option}-id",
                        "label": {"text": option},
                        "value": option,
                    }
                    for option in question_data["select_options"]
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
        # the summary uses this to identify the response
        response_name = f"resp-{response_name}"

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

        return render_template(
            "question_template.html", **mapped_question.to_dict()
        )
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
        # print("Response session data NOT found")
        session["response"] = {}

    if "survey" not in session:
        # print("Survey session data NOT found")
        session["survey"] = user_survey

        # Set the time start based on the current timestamp
        session["survey"]["survey"]["time_start"] = datetime.now(timezone.utc)
        session.modified = True
    elif session["current_question_index"] == 0:
        session["survey"]["survey"]["time_start"] = datetime.now(timezone.utc)
        session.modified = True

    print("Save Response Survey time_start:", session["survey"]["survey"]["time_start"])

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
            "organisation_type", "organisation-type", "summary"
        ),  # TODO onward route needs to be dynamic (changed from survey to summary)
        "longer_hours_question": lambda: update_session_and_redirect(
            "longer_hours", "longer-hours", "summary"
        ),
        "survey_assist_consent": lambda: consent_redirect(),
        "follow_up_question": lambda: followup_redirect(),
    }

    # Store the user response to the question AI asked
    question = request.form.get("question_name")
    # print("Question:", question)

    if question.startswith("ai_assist"):
        question = "follow_up_question"

        # get survey data
        survey_data = session.get("survey")
        # get questions
        questions = survey_data["survey"]["questions"]

        # get the last question
        last_question = questions[-1]
        # update the response name, required by forward_redirect
        # TODO - can this be incorporated in the forward_redirect function?
        last_question["response"] = request.form.get(last_question["response_name"])

    if question in actions:
        return actions[question]()
    else:
        return "Invalid question ID", 400


# Make a final API request to get the results of the survey assist
@app.route("/survey_assist_results", methods=["GET", "POST"])
def survey_assist_results():

    # Get the survey data from the session
    user_survey = session.get("survey")
    survey_questions = user_survey["survey"]["questions"]

    # print("Survey questions:", survey_questions)

    html_output = "<strong> ERROR ERROR ERROR </strong>"
    # check the survey assist responses exist in the session
    if "sa_response" in session:
        sa_response = session.get("sa_response")
        print("SA Response:", sa_response)

        survey_responses = session.get("survey")

        print("Survey_assist_results")
        print("Time start:", survey_responses["survey"]["time_start"])
        print("Time end:", survey_responses["survey"]["time_end"])
        print("Survey Assist Time Start:", survey_responses["survey"]["survey_assist_time_start"])
        print("Survey Assist Time End:", survey_responses["survey"]["survey_assist_time_end"])

        # Calculate the time taken to answer the survey
        time_taken = (
            survey_responses["survey"]["time_end"]
            - survey_responses["survey"]["time_start"]
        ).total_seconds()

        # Calculate the time taken to interact with Survey Assist
        survey_assist_time = (
            survey_responses["survey"]["survey_assist_time_end"]
            - survey_responses["survey"]["survey_assist_time_start"]
        ).total_seconds()

        # Find the SIC classification questions from the survey
        classification_questions = get_questions_by_classification(survey_data, "sic")
        filtered_responses = filter_classification_responses(survey_responses, classification_questions)

        print("Filtered responses:", filtered_responses)

        # Copy the filtered responses dictionary
        updated_responses = copy.deepcopy(filtered_responses)

        print("Updated responses:", updated_responses)
        # In updated_responses, find the org description
        # question
        org_description_question = [question for question in updated_responses if question["question_text"].startswith("At your main job, describe the main activity of the business")]
        if org_description_question:
            print("Organisation description:", org_description_question[0]["response"])

        # search survey_questions and get a list of the questions whose
        # question_id starts with "f"
        followup_questions = [question for question in survey_questions if question["question_id"].startswith("f")]

        # If follow up questions were asked print them
        print("Follow-up questions:", followup_questions)

        for question in followup_questions:
            if question["response_type"] == "text":
                # Add the response to the organisation description
                org_description_question[0]["response"] += f". {question['response']}"
            elif question["response_type"] == "radio":
                if question["response"] == "none of the above":
                    for response in question["response_options"]:
                        if response["value"] != "none of the above":
                            # Add the response to the organisation description
                            org_description_question[0]["response"] += f". Organisation is NOT {response['value']}"
                else:
                    # Add the response to the organisation description
                    org_description_question[0]["response"] += f". Organisation is {question['response']}"

        # copy the sa_response and remove the first entry of
        # the candidates
        # TODO - this removes the first candidate, the copy is not needed
        # as it is not a deep copy and sa_response_presentation is not used
        sa_response_presentation = sa_response.copy()
        sa_response_presentation["categorisation"]["codings"] = sa_response_presentation["categorisation"]["codings"][1:]

        # print("Filtered responses:", filtered_responses)
        html_output = render_classification_results(sa_response,
                                                    filtered_responses,
                                                    time_taken,
                                                    survey_assist_time)

        sa_result = [{"interaction": "classification", "type": "sic", "title": "Initial SIC", "html_output": html_output}]

        print("Updated organisation description:", org_description_question[0]["response"])

        filtered_responses[2]["response"] = org_description_question[0]["response"]

        updated_classification = get_classification("gemini", "sic", filtered_responses)

        print("Updated classification:", updated_classification)

        updated_api_response = map_api_response_to_internal(updated_classification)

        # Remove the first candidate from the classification
        updated_api_response["categorisation"]["codings"] = updated_api_response["categorisation"]["codings"][1:]

        # TODO - need to store updated_api_response and sa_response
        # in the session data so they can be saved to the API

        # Render the updated classification results
        html_output = render_classification_results(updated_api_response,
                                                    filtered_responses,
                                                    time_taken,
                                                    survey_assist_time)

        sa_result.insert(0, {"interaction": "classification", "type": "final-sic", "title": "Final - SIC", "html_output": html_output})

        return render_template("classification_template.html", 
                               sa_result=sa_result)
    else:
        print("Session data not found")
        return redirect(url_for("thank_you", survey=SURVEY_NAME))


# Route to make an API request (used for testing)
@app.route("/save_results", methods=["GET", "POST"])
def save_results():

    # print the method used
    # print("SAVE SAVE SAVE - save_results "+request.method)

    survey_data = session.get("survey")

    time_dict = {
        "time_start": survey_data["survey"]["time_start"],
        "time_end": survey_data["survey"]["time_end"],
        "survey_assist_time_start": survey_data
        ["survey"]["survey_assist_time_start"],
        "survey_assist_time_end": survey_data
        ["survey"]["survey_assist_time_end"],
    }
    fields = ["time_start", "time_end", "survey_assist_time_start", "survey_assist_time_end"]
    times = datetime_to_string(time_dict, fields)
    print("=====TIMES=====")
    print(times)
    print("================")

    print("========BODY========")
    print("user_id:", USER_ID)
    print("survey_name:", SURVEY_NAME)
    print("time_start:", times["time_start"])
    print("time_end:", times["time_end"])
    print("survey_assist_time_start:", times["survey_assist_time_start"])
    print("survey_assist_time_end:", times["survey_assist_time_end"])
    print("survey_schema - core questions", questions)
    print("survey_schema - survey assist", ai_assist)
    print("survey_response - questions", survey_data["survey"]["questions"])
    print("====================")
    api_url = "http://127.0.0.1:5000/survey-assist/response"
    body = {
        "user_id": USER_ID,
        "survey_responses": [
            {
                "survey_name": SURVEY_NAME,
                "responses": [
                    {
                        "time_start": times["time_start"],
                        "time_end": times["time_end"],
                        "survey_assist_time_start": times["survey_assist_time_start"],
                        "survey_assist_time_end": times["survey_assist_time_end"],
                        "survey_schema": {
                            "core_questions": questions,
                            "survey_assist": ai_assist
                        },
                        "survey_response": {
                            "questions": survey_data["survey"]["questions"]
                        }
                    }
                ]
            }
        ],
    }

    # make an api request
    try:
        # Send a request to the Survey Assist API
        response = requests.post(api_url, json=body, timeout=API_TIMER_SEC)

        if response.status_code != HTTPStatus.OK or not response.json():
            return redirect(url_for("error_page"))

        response_data = response.json()

        return render_template("thank_you.html", survey=SURVEY_NAME)

    except Exception as e:
        print("Error occurred:", e)
        return redirect(url_for("error_page"))


# The survey route takes summarises the data that has been
# entered by user, using the session data held in the survey
# dictionary. The data is then displayed in a summary template
@app.route("/summary")
def summary():
    print_session()
    survey_data = session.get("survey")
    survey_questions = survey_data["survey"]["questions"]

    # Print warning when time_start is not set
    if survey_data["survey"]["time_start"] is None:
        print("WARNING: Survey - time_start is not set")

    # Calculate the time_end based on the current timestamp
    survey_data["survey"]["time_end"] = datetime.now(timezone.utc)
    session.modified = True

    print(survey_data["survey"]["time_start"], survey_data["survey"]["time_start"].tzinfo)
    print(survey_data["survey"]["time_end"], survey_data["survey"]["time_end"].tzinfo)

    # Print the time taken in seconds to answer the survey
    time_taken = (survey_data["survey"]["time_end"] - survey_data["survey"]["time_start"]).total_seconds()
    print("--------TIMING--------")
    print("Time taken to complete survey:", time_taken)
    print("----------------------")

    # Loop through the questions, when a question_name starts with ai_assist
    # uppdate the question_text to have a label added to say it was generated by
    # Survey Assist
    for question in survey_questions:
        if question["response_name"].startswith("resp-ai-assist"):
            question["question_text"] = (
                question["question_text"] + ai_assist["question_assist_label"]
            )

    # print("Survey questions:", survey_questions)
    return render_template("summary_template.html", questions=survey_questions)


@app.route("/survey_assist_consent")
def survey_assist_consent():
    # print("AI Assist consent " + str(ai_assist))

    # Get the survey data from the session
    user_survey = session.get("survey")

    print("Survey time start in survey_assist_consent:", user_survey["survey"]["time_start"])

    # Mark the survey assist time start
    user_survey.get("survey")["survey_assist_time_start"] = datetime.now(timezone.utc)
    session.modified = True

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
        ai_assist["consent"]["question_text"] = ai_assist["consent"][
            "question_text"
        ].replace("PLACEHOLDER_FOLLOWUP", followup_text)

    if "PLACEHOLDER_REASON" in ai_assist["consent"]["question_text"]:
        # Replace PLACEHOLDER_REASON wit the content of the placeholder field
        ai_assist["consent"]["question_text"] = ai_assist["consent"][
            "question_text"
        ].replace("PLACEHOLDER_REASON", ai_assist["consent"]["placeholder_reason"])

    # print("AI Assist consent question text:", ai_assist["consent"]["question_text"])
    return render_template(
        "survey_assist_consent.html",
        title=ai_assist["consent"]["title"],
        question_name=ai_assist["consent"]["question_name"],
        question_text=ai_assist["consent"]["question_text"],
        justification_text=ai_assist["consent"]["justification_text"],
    )


@app.route("/classification")
def classification():
    return render_template("classification_template.html")
    # print_session()
    # survey_data = session.get("survey")
    # survey_questions = survey_data["survey"]["questions"]

    # # Loop through the questions, when a question_name starts with ai_assist
    # # uppdate the question_text to have a label added to say it was generated by
    # # Survey Assist
    # for question in survey_questions:
    #     if question["response_name"].startswith("resp-ai-assist"):
    #         question["question_text"] = (
    #             question["question_text"] + ai_assist["question_assist_label"]
    #         )

    # return render_template("classification_template.html", questions=survey_questions)

# Rendered at the end of the survey
@app.route("/thank_you")
def thank_you():
    print_session()
    return render_template("thank_you.html", survey=SURVEY_NAME)


# Route to handle errors
@app.route("/error")
def error_page():
    return "An error occurred. Please try again later."


def consent_redirect():
    user_survey = session.get("survey")

    # Get the form value for survey_assist_consent
    consent_response = request.form.get("survey-assist-consent")

    # Add the consent response to the survey
    user_survey["survey"]["questions"].append(
        {
            "question_id": ai_assist["consent"]["question_id"],
            "question_text": ai_assist["consent"]["question_text"],
            "response_type": "radio",
            "response_name": "survey-assist-consent",
            "response_options": [
                {"id": "consent-yes", "label": {"text": "Yes"}, "value": "yes"},
                {"id": "consent-no", "label": {"text": "No"}, "value": "no"},
            ],
            "response": consent_response,
        }
    )

    session.modified = True

    if consent_response == "yes":
        # print("User consented to AI Assist")
        return redirect(url_for("survey_assist"))
    else:
        # print("User did not consent to AI Assist")
        # Mark the end time for the survey assist
        user_survey.get("survey")["survey_assist_time_end"] = datetime.now(timezone.utc)

        # Skip to next standard question
        session["current_question_index"] += 1
        session.modified = True
        return redirect(url_for("survey"))


# TODO - This is currently only checking the first interaction, need to search
# for the current question in the interactions list.
def followup_redirect():
    current_question = questions[session["current_question_index"]]
    # print("followup current_question:", current_question.get("question_id"))

    interactions = ai_assist.get("interactions")
    # Check if the current question has a follow-up question
    # TODO - this is currently only checking the first interaction
    if len(interactions) > 0 and current_question.get("question_id") == interactions[
        0
    ].get("after_question_id"):
        # print("=== FOLLOW UP PROCESSING ===")

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

        # Check if the session has follow-up questions
        if "follow_up" in session and FOLLOW_UP_TYPE == "both":
            follow_up = session["follow_up"]
            if len(follow_up) > 0:
                # Get the next follow-up question
                follow_up_question = follow_up.pop(0)
                # print("Follow-up question:", follow_up_question)

                # The response is mapped into a question object
                # which is then added to the dynamic survey data
                # TODO - make a function to handle this
                mapped_question = Question(
                    question_id=follow_up_question["follow_up_id"],
                    question_name=follow_up_question["question_name"],
                    question_title=follow_up_question["question_name"],
                    question_text=follow_up_question["question_text"],
                    question_description="This question is generated by Survey Assist",
                    response_type=follow_up_question["response_type"],
                    response_options=(
                        [
                            {
                                "id": f"{option}-id",
                                "label": {"text": option},
                                "value": option,
                            }
                            for option in follow_up_question["select_options"]
                        ]
                        if follow_up_question["response_type"] == "select"
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

                return render_template(
                    "question_template.html", **mapped_question.to_dict()
                )

        # Mark the end time for the survey assist
        survey_data.get("survey")["survey_assist_time_end"] = datetime.now(timezone.utc)

        # increment the current question index to
        # get the next question
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
            "survey_assist_time_start": None,
            "survey_assist_time_end": None,
        }
        user_survey = session["survey"]
        # Set the time start based on the current timestamp
        user_survey["time_start"] = datetime.now(timezone.utc)
        print("Initialise survey data in update_session_and_redirect")
        print("Survey data:", session.get("survey"))
        session.modified = True


    # Get the current question and take a copy so
    # that the original question data is not modified
    current_question = questions[session["current_question_index"]]
    current_question = current_question.copy()

    placeholder_field = current_question["placeholder_field"]

    if "response" in session and placeholder_field in session["response"]:
        current_question["question_text"] = current_question["question_text"].replace(
            "PLACEHOLDER_TEXT", session["response"][placeholder_field]
        )
        # print("Updated question text:", current_question["question_text"])

    # Append the question and response to the list of questions
    user_survey["survey"]["questions"].append(
        {
            "question_id": current_question.get("question_id"),
            "question_text": current_question.get("question_text"),
            "response_type": current_question.get("response_type"),
            "response_options": current_question.get("response_options"),
            "response_name": current_question.get("response_name"),
            "response": request.form.get(value),
            "used_for_classifications": current_question.get("used_for_classifications"),
        }
    )

    # If ai assist is enabled and the current question has an interaction
    # then redirect to the consent page to ask the user if they want to
    # continue with the AI assist interaction
    if ai_assist.get("enabled", True):
        session.modified = True
        interactions = ai_assist.get("interactions")
        if len(interactions) > 0:
            # print("Interactions:", interactions[0])
            # print("current_question:", current_question.get("question_id"))
            # print("interaction id:", interactions[0].get("after_question_id"))

            if current_question.get("question_id") == interactions[0].get(
                "after_question_id"
            ):
                # print("AI Assist interaction detected - REDIRECTING to consent")
                return redirect(url_for("survey_assist_consent"))

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
