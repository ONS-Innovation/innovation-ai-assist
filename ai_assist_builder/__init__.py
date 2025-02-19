import copy
import os
from datetime import datetime, timezone
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
from google.cloud import storage
from markupsafe import escape

from ai_assist_builder.models.api_map import map_api_response_to_internal
from ai_assist_builder.models.question import Question
from ai_assist_builder.utils.classification_utils import (
    filter_classification_responses,
    get_classification,
    get_last_survey_response,
    get_questions_by_classification,
    save_classification_response,
    update_last_survey_response,
)
from ai_assist_builder.utils.debug_utils import (
    log_api_rcv,
    log_api_send,
    log_session,
    mask_username,
    print_session,
    print_session_size,
)
from ai_assist_builder.utils.jwt_utils import (
    check_and_refresh_token,
    current_utc_time,
    generate_jwt,
)
from ai_assist_builder.utils.log_utils import log_entry, setup_logging
from ai_assist_builder.utils.results_utils import (
    calculate_average_excluding_max,
    count_sic_changes,
    count_test_ids_by_user,
    filter_and_split_dataframe,
    format_users_for_checkboxes,
    generate_results_filename,
    generate_test_results_df,
    generate_user_cards,
    process_users,
    stream_file_from_store,
)
from ai_assist_builder.utils.template_utils import (
    datetime_to_string,
    render_classification_results,
    render_sic_lookup_results,
    render_sic_lookup_unsuccessful,
)

SESSION_LIMIT = 10700
DEBUG = True
TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_THRESHOLD = 300  # 5 minutes
API_TIMER_SEC = 30
FOLLOW_UP_TYPE = "both"  # closed or open or both
SURVEY_NAME = "TLFS PoC"
DEFAULT_ENDPOINT = "classify-v3"

# Setup logging
logger = setup_logging("flask")

number_to_word = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
jwt_secret_path = os.getenv("JWT_SECRET")
sa_email = os.getenv("SA_EMAIL")

# TODO - Rationalise
backend_api_url = os.getenv("BACKEND_API_URL", "http://127.0.0.1:5000")
api_gateway = os.getenv("API_GATEWAY")

token_start_time = current_utc_time()
# Generate JWT (lasts 1 hour - TODO rotate before expiry)
jwt_token = generate_jwt(
    jwt_secret_path, audience=api_gateway, sa_email=sa_email, expiry_length=TOKEN_EXPIRY
)
# Print the last 5 digits of the jwt token
print(f"JWT Token ends with {jwt_token[-5:]} created at {token_start_time}")

# Load the questions from the JSON file
with open("ai_assist_builder/content/condensed_tlfs_sic_soc.json") as file:
    survey_data = json.load(file)
    questions = survey_data["questions"]
    ai_assist = survey_data["ai_assist"]


# Initialise user survey data
# TODO - make a utility function
user_survey = {
    "survey": {
        "user": "",
        "questions": [],
        "time_start": None,
        "time_end": None,
        "survey_assist_time_start": None,
        "survey_assist_time_end": None,
    }
}

Misaka(app)

app.jinja_env.add_extension("jinja2.ext.do")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["FREEZER_IGNORE_404_NOT_FOUND"] = True
app.config["FREEZER_DEFAULT_MIMETYPE"] = "text/html"
app.config["FREEZER_DESTINATION"] = "../build"
app.cache = {}

# GCP Bucket and File Info
BUCKET_NAME = "sandbox-survey-assist"
USERS_FILE = "users.json"
storage_client = storage.Client()


# Check the JWT token status before processing the request
@app.before_request
def before_request():
    global token_start_time, jwt_token
    """Check token status before processing the request."""
    token_start_time, jwt_token = check_and_refresh_token(
        token_start_time, jwt_token, jwt_secret_path, api_gateway, sa_email
    )

    # Log the request method and route
    logger.debug(f"Rx Method: {request.method} - Route: {request.endpoint}")


@app.route("/save_as_csv", methods=["GET", "POST"])
def save_as_csv():
    # Get the result_selection from the session data
    result_selection = session.get("result_selection", {})
    users = result_selection.get("users", [])
    start_date = result_selection.get("start_date", "")

    all_results = process_users(
        bucket_name=BUCKET_NAME,
        base_folder="TLFS_PoC",
        users=users,
        start_date=start_date,
    )

    if all_results:
        # Generate a dataframe with results
        df = generate_test_results_df(all_results, detailed=True)

        results_path = generate_results_filename(
            user=session["user"], base_folder="TLFS_PoC"
        )

        # Save to store
        filter_and_split_dataframe(df, BUCKET_NAME, results_path, drop_columns=True)

        return stream_file_from_store(BUCKET_NAME, results_path)
    else:
        return redirect(url_for("error_page", error="No results found"))


# TODO - refactor
# Render the results page
@app.route("/get_result", methods=["POST"])
def get_result():

    print(f"Request form: {request}")
    day = request.form.get("day")
    month = request.form.get("month")
    year = request.form.get("year")

    # if day, month or year is not populated, return an error
    if not day or not month or not year:
        return redirect(url_for("error_page", error="Date not selected"))

    users = request.form.getlist("users")

    if "users" not in request.form:
        return redirect(url_for("error_page", error="No users selected"))

    # Print the values with a string
    print(f"Day: {day}, Month: {month}, Year: {year}, Users: {users}")

    start_date = f"{day}-{month}-{year}"

    # Add the start date and users to the session data
    if "result_selection" not in session:
        session["result_selection"] = {}

    session["result_selection"]["start_date"] = start_date
    session["result_selection"]["users"] = users
    session.modified = True

    all_results = process_users(
        bucket_name=BUCKET_NAME,
        base_folder="TLFS_PoC",
        users=users,
        start_date=start_date,
    )

    if all_results:
        # Generate a dataframe with results
        df = generate_test_results_df(all_results, detailed=True)

        # Build a results dictionary for presentation
        results = {
            "user_totals": [{}],
        }
        results["total_tests"] = len(df)

        for user in users:
            user_total = count_test_ids_by_user(user, df)
            results["user_totals"].append({"user": user, "total": user_total})

        sic_changes = count_sic_changes(df)
        results["sic_same"] = sic_changes["same"]
        results["sic_different"] = sic_changes["different"]
        results["avg_interaction_time"] = round(calculate_average_excluding_max(df), 1)

        sic_lookup_counts = {
            "True": df["SIC_Lookup_Status"].eq(True).sum(),
            "False": df["SIC_Lookup_Status"].eq(False).sum(),
            "None": df["SIC_Lookup_Status"].isna().sum(),
        }

        results["sic_lookup_total_tests"] = (
            sic_lookup_counts["True"] + sic_lookup_counts["False"]
        )
        results["sic_lookup_found"] = sic_lookup_counts["True"]
        results["sic_lookup_not_found"] = sic_lookup_counts["False"]

    else:
        # TODO - simplify
        results = {
            "user_totals": [{}],
        }

        results["total_tests"] = 0
        for user in users:
            user_total = 0
            results["user_totals"].append({"user": user, "total": user_total})

        results["sic_same"] = 0
        results["sic_different"] = 0
        results["avg_interaction_time"] = 0
        results["sic_lookup_total_tests"] = 0
        results["sic_lookup_found"] = 0
        results["sic_lookup_not_found"] = 0

    results["users_html"] = generate_user_cards(results["user_totals"])

    testing_users = get_users_by_roles("admin", "tester")
    print(f"Testing users: {testing_users}")
    user_checkboxes = format_users_for_checkboxes(testing_users)
    return render_template(
        "testing_admin.html", results=results, user_checkboxes=user_checkboxes
    )


# Only allowed for admin and tester roles
@app.route("/testing_admin", methods=["GET", "POST"])
def testing_admin():
    if request.method == "POST":
        print(f"Request form: {request}")

    # Get the role of the user
    role = session.get("role")
    print(f"Role: {role}")
    if role not in ["admin", "tester"]:
        return redirect(url_for("error_page", error="Not authorised for test data"))

    testing_users = get_users_by_roles("admin", "tester")
    print(f"Testing users: {testing_users}")

    user_checkboxes = format_users_for_checkboxes(testing_users)

    print(f"User checkboxes: {user_checkboxes}")
    return render_template("testing_admin.html", user_checkboxes=user_checkboxes)


@app.route("/ons_mockup", methods=["GET"])
def ons_mockup():

    # Get the role of the user
    role = session.get("role")
    print(f"Role: {role}")
    if role not in ["admin", "tester"]:
        return render_template("error_ons_mockup.html")

    return render_template("ons_mockup.html")


@app.route("/config", methods=["GET", "POST"])
def config():  # noqa: PLR0911
    if request.method == "POST":
        print(f"Selected: {request.form.get("api-version")}")
        session["endpoint"] = (
            "classify" if request.form.get("api-version") == "v1v2" else "classify-v3"
        )
        print(f"Classify endpoint: {session['endpoint']}")
        session["follow_up_type"] = request.form.get("follow-up-question")
        print(f"Follow-up question on post: {session['follow_up_type']}")
        # Reset the consent question text
        # Ideally we would read this from the json again
        ai_assist["consent"][
            "question_text"
        ] = "Can Survey Assist ask PLACEHOLDER_FOLLOWUP to better understand PLACEHOLDER_REASON?"
        session.modified = True
        applied = True
    else:
        applied = False

    # Get the config from the backend
    api_url = backend_api_url + "/survey-assist/config"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    log_api_send(logger, api_url, None)
    try:
        response = requests.get(api_url, headers=headers, timeout=API_TIMER_SEC)
        response_data = response.json()

        log_api_rcv(logger, api_url, response_data)

        # Get v1/v2 prompt
        v1v2prompt = "<strong>RAG</strong><p></p>" + response_data["v1v2"][
            "classification"
        ][0]["prompts"][0]["text"].replace("\n", "<br>")
        v3prompt = (
            "<strong>Reranker</strong><p></p>"
            + response_data["v3"]["classification"][0]["prompts"][0]["text"].replace(
                "\n", "<br>"
            )
            + "<strong>Unambiguous</strong><p></p>"
            + response_data["v3"]["classification"][0]["prompts"][1]["text"].replace(
                "\n", "<br>"
            )
        )

        config = {
            "selected_version": session["endpoint"],
            "follow_up_type": session["follow_up_type"],
            "applied": applied,
            "model": response_data.get("llm_model"),
            "v1v2prompt": v1v2prompt,
            "v3prompt": v3prompt,
        }

        # Get the role of the user
        role = session.get("role")
        if role not in ["cash"]:
            logger.error(
                f"User {mask_username(session['user'])} not authorised for config"
            )
            return redirect(url_for("error_page", error="Not authorised for config"))

        logger.info(
            f"Config settings - selected_version: {config['selected_version']} follow_up_type: {config['follow_up_type']} model: {config['model']} applied: {config['applied']}"
        )

        return render_template(
            "config.html",
            config=config,
        )

    except requests.exceptions.Timeout:
        return jsonify({"error": "The request timed out. Please try again later."}), 504
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {"error": "Failed to connect to the API. Please check your connection."}
            ),
            502,
        )
    except requests.exceptions.HTTPError as http_err:
        return (
            jsonify({"error": f"HTTP error occurred: {http_err.response.status_code}"}),
            500,
        )
    except ValueError:
        # For JSON decoding errors
        return jsonify({"error": "Failed to parse the response from the API."}), 500
    except KeyError as key_err:
        # This can be invalid JWT, check GCP logs
        return (
            jsonify(
                {"error": f"Missing expected data: {str(key_err)}"}  # noqa: RUF010
            ),
            500,
        )
    except Exception as e:
        return (
            jsonify({"error": e}),
            500,
        )


@app.route("/chat_service", methods=["GET"])
def chat_service():
    return render_template("chat_service.html")


@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/check_login", methods=["POST"])
def check_login():
    # Get email and convert to lowercase
    email = request.form.get("email-username").lower()
    password = request.form.get("password")

    if validate_user(email, password):
        session["user"] = email
        session["role"] = get_user_role(email)
        print(f"User {email.split("@")[0]} logged in with role {session['role']}")
        session["endpoint"] = DEFAULT_ENDPOINT
        session["follow_up_type"] = FOLLOW_UP_TYPE
        session.modified = True
        return redirect("/")
    else:
        return render_template(
            "login.html", error="Invalid credentials. Please try again."
        )


@app.route("/")
def index():
    if "follow_up_type" not in session:
        session["follow_up_type"] = FOLLOW_UP_TYPE

    if "user" not in session:
        return redirect("/login")
    # When the user navigates to the home page, reset the session data
    if "current_question_index" in session:
        # Reset the current question index in the session
        session["current_question_index"] = 0

    # Clear the response data in the session
    if "response" in session:
        session.pop("response")

    if "survey" in session:
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

    if "sa_response" in session:
        session["sa_response"] = []

    # Clear the follow-up questions in the session
    if "follow_up" in session:
        session.pop("follow_up")

    if "sic_lookup" in session:
        session.pop("sic_lookup")

    session.modified = True

    if print_session_size() > SESSION_LIMIT:
        print_session()

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
    print("/survey")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    # Initialize the current question index in the session if it doesn't exist
    if "current_question_index" not in session:
        session["current_question_index"] = 0

        session.modified = True

    # Get the current question based on the index
    current_index = session["current_question_index"]
    current_question = questions[current_index]

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

    return render_template("question_template.html", **current_question)


@app.route("/chat_lookup", methods=["POST"])
def chat_lookup():  # noqa: PLR0911
    print("/chat_lookup")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    chat_response = request.json
    org_description = chat_response.get("org_description")

    api_url = (
        backend_api_url
        + f"/survey-assist/sic-lookup?description={org_description}&similarity=true"
    )
    headers = {"Authorization": f"Bearer {jwt_token}"}
    log_api_send(logger, api_url, None)
    try:
        response = requests.get(api_url, headers=headers, timeout=API_TIMER_SEC)
        response_data = response.json()

        log_api_rcv(logger, api_url, response_data)
        return response_data
    except requests.exceptions.Timeout:
        return jsonify({"error": "The request timed out. Please try again later."}), 504
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {"error": "Failed to connect to the API. Please check your connection."}
            ),
            502,
        )
    except requests.exceptions.HTTPError as http_err:
        return (
            jsonify({"error": f"HTTP error occurred: {http_err.response.status_code}"}),
            500,
        )
    except ValueError:
        # For JSON decoding errors
        return jsonify({"error": "Failed to parse the response from the API."}), 500
    except KeyError as key_err:
        # This can be invalid JWT, check GCP logs
        return (
            jsonify(
                {"error": f"Missing expected data: {str(key_err)}"}  # noqa: RUF010
            ),
            500,
        )
    except Exception:
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


@app.route("/chat_assist", methods=["POST"])
def chat_assist():  # noqa: PLR0911
    print("/chat_assist")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    llm = "gemini"  # gemini or chat-gpt
    type = "sic"  # sic or soc or sic_soc

    # Find the question about job_title
    user_response = request.json

    api_url = backend_api_url + f"/survey-assist/{session["endpoint"]}"

    body = {
        "llm": llm,
        "type": type,
        "job_title": user_response.get("job_title"),
        "job_description": user_response.get("job_description"),
        "org_description": user_response.get("org_description"),
    }
    headers = {"Authorization": f"Bearer {jwt_token}"}

    log_api_send(logger, api_url, body)
    try:
        # Send a request to the Survey Assist API
        response = requests.post(
            api_url, json=body, headers=headers, timeout=API_TIMER_SEC
        )
        response.raise_for_status()  # Raise an error for HTTP codes 4xx/5xx
        response_data = response.json()
        log_api_rcv(logger, api_url, response_data)

        # Return the result back to the chatbot
        return (
            jsonify(
                {
                    "followup": response_data["followup"],
                    "sic_code": response_data["sic_code"],
                    "sic_description": response_data["sic_description"],
                    "sic_candidates": response_data["sic_candidates"],
                    "reasoning": response_data["reasoning"],
                }
            ),
            200,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "The request timed out. Please try again later."}), 504
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {"error": "Failed to connect to the API. Please check your connection."}
            ),
            502,
        )
    except requests.exceptions.HTTPError as http_err:
        return (
            jsonify({"error": f"HTTP error occurred: {http_err.response.status_code}"}),
            500,
        )
    except ValueError:
        # For JSON decoding errors
        return jsonify({"error": "Failed to parse the response from the API."}), 500
    except KeyError as key_err:
        # This can be invalid JWT, check GCP logs
        return (
            jsonify(
                {"error": f"Missing expected data: {str(key_err)}"}  # noqa: RUF010
            ),
            500,
        )
    except Exception:
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


# A generic route that handles survey interactions (e.g call to AI)
# TODO - split out to functions
@app.route("/survey_assist", methods=["GET", "POST"])
def survey_assist():  # noqa: C901, PLR0911

    llm = "gemini"  # gemini or chat-gpt
    type = "sic"  # sic or soc or sic_soc

    # Find the question about job_title
    user_response = session.get("response")

    api_url = backend_api_url + f"/survey-assist/{session["endpoint"]}"

    body = {
        "llm": llm,
        "type": type,
        "job_title": user_response.get("job_title"),
        "job_description": user_response.get("job_description"),
        "org_description": user_response.get("organisation_activity"),
    }
    headers = {"Authorization": f"Bearer {jwt_token}"}
    log_api_send(logger, api_url, body)

    try:
        # Send a request to the Survey Assist API
        response = requests.post(
            api_url, json=body, headers=headers, timeout=API_TIMER_SEC
        )
        response_data = response.json()
        log_api_rcv(logger, api_url, response_data)

        api_response = map_api_response_to_internal(response_data)

        followup_questions = api_response.get("follow_up", {}).get("questions", [])

        # If at least one question is available, loop through the questions
        # and print the question text
        if followup_questions:

            # Store the internal survey assist response in the session
            save_classification_response(session, api_response)

            # Add the follow-up questions to the session data
            # first check if the follow-up questions are already
            # in the session data
            if "follow_up" not in session:
                session["follow_up"] = []

            session["follow_up"].extend(followup_questions)
            session.modified = True

        if session["follow_up_type"] in ["open", "both"]:
            followup = session.get("follow_up", {})
            question_data = followup.pop(0)
            question_text = question_data.get("question_text", "")
        elif session["follow_up_type"] == "closed":
            followup = session.get("follow_up", {})
            question_data = followup.pop(-1)
            question_text = question_data.get("question_text", "")

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

        print("/survey_assist")
        if print_session_size() > SESSION_LIMIT:
            print_session()

        return render_template("question_template.html", **mapped_question.to_dict())

    except requests.exceptions.Timeout:
        return jsonify({"error": "The request timed out. Please try again later."}), 504
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {"error": "Failed to connect to the API. Please check your connection."}
            ),
            502,
        )
    except requests.exceptions.HTTPError as http_err:
        return (
            jsonify({"error": f"HTTP error occurred: {http_err.response.status_code}"}),
            500,
        )
    except ValueError:
        # For JSON decoding errors
        return jsonify({"error": "Failed to parse the response from the API."}), 500
    except KeyError as key_err:
        # This can be invalid JWT, check GCP logs
        return (
            jsonify(
                {"error": f"Missing expected data: {str(key_err)}"}  # noqa: RUF010
            ),
            500,
        )
    except Exception:
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


# Route called after each question (or interaction) to save response to session data.
# The response is saved to the session dictionary and the user is redirected to the
# next question or interaction.
# TODO - The actions dictionary is currently hardcoded for survey questions, this
# needs to be updated to be more dynamic.  There is also cruft in the variables passed
# to the update_session_and_redirect function.
@app.route("/save_response", methods=["POST"])
def save_response():

    print("/save_response (entry)")
    if print_session_size() > SESSION_LIMIT:
        print_session()

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

    print("/save_response (exit)")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    if question in actions:
        return actions[question]()
    else:
        return "Invalid question ID", 400


# Used to save the sic lookup result to the backed
@log_entry(logger)
def format_lookup_response(sic_lookup_response):

    lookup_result = {
        "interaction": "lookup",
        "type": "sic",
        "lookup_string": sic_lookup_response["org_description"],
        "found": False,
        "response": {},
    }

    # If sic found
    if sic_lookup_response["sic_code"] is not None:
        lookup_result["found"] = True
        lookup_result["response"] = {
            "sic_code": sic_lookup_response["sic_code"],
            "sic_code_meta": sic_lookup_response["sic_code_meta"],
            "sic_code_division_meta": sic_lookup_response["sic_code_division_meta"],
        }
    else:
        lookup_result["response"] = {
            "potential_sic_codes_count": sic_lookup_response[
                "potential_sic_codes_count"
            ],
            "potential_sic_divisions_count": sic_lookup_response[
                "potential_sic_divisions_count"
            ],
            "potential_sic_codes": sic_lookup_response["potential_sic_codes"],
            "potential_sic_divisions": sic_lookup_response["potential_sic_divisions"],
        }

    return lookup_result


# Used to display the SIC lookup results on the UI
@log_entry(logger)
def create_lookup_result(sic_lookup_response):

    # If sic found
    if sic_lookup_response["sic_code"] is not None:
        html_output = render_sic_lookup_results(
            sic_lookup_response["org_description"],
            sic_lookup_response["sic_code"],
            sic_lookup_response["sic_code_meta"],
            sic_lookup_response["sic_code_division_meta"],
        )
    else:
        html_output = render_sic_lookup_unsuccessful(
            sic_lookup_response["org_description"],
            sic_lookup_response["potential_sic_codes_count"],
            sic_lookup_response["potential_sic_divisions_count"],
            sic_lookup_response["potential_sic_codes"],
            sic_lookup_response["potential_sic_divisions"],
        )

    lookup_result = {
        "interaction": "classification",
        "type": "sic-lookup",
        "title": "SIC Lookup",
        "html_output": html_output,
    }

    return lookup_result


# Make a final API request to get the results of the survey assist
# TODO - refactor
@app.route("/survey_assist_results", methods=["GET", "POST"])
def survey_assist_results():  # noqa: C901, PLR0912, PLR0915

    print("/survey_assist_results (entry)")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    # Get the survey data from the session
    user_survey = session.get("survey")
    survey_questions = user_survey["survey"]["questions"]

    # print("Survey questions:", survey_questions)

    html_output = "<strong> ERROR ERROR ERROR </strong>"
    # check the survey assist responses exist in the session
    if "sa_response" in session:
        sa_response_list = session.get("sa_response", [])
        if sa_response_list:
            sa_response = sa_response_list[0]
        else:
            print("No responses in sa_response.")

        survey_responses = session.get("survey")

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
        filtered_responses = filter_classification_responses(
            survey_responses, classification_questions
        )

        print("Filtered responses:", filtered_responses)

        # Copy the filtered responses dictionary
        updated_responses = copy.deepcopy(filtered_responses)

        print("Updated responses:", updated_responses)
        # In updated_responses, find the org description
        # question
        ORG_QUESTION = "At your main job, describe the main activity of the business"
        org_description_question = [
            question
            for question in updated_responses
            if question["question_text"].startswith(ORG_QUESTION)
        ]
        if org_description_question:
            print("Organisation description:", org_description_question[0]["response"])

        # search survey_questions and get a list of the questions whose
        # question_id starts with "f"
        followup_questions = [
            question
            for question in survey_questions
            if question["question_id"].startswith("f")
        ]

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
                            org_description_question[0][
                                "response"
                            ] += f". Organisation is NOT {response['value']}"
                else:
                    # Add the response to the organisation description
                    org_description_question[0][
                        "response"
                    ] += f". Organisation is {question['response']}"

        # copy the sa_response and remove the first entry of
        # the candidates
        # TODO - this removes the first candidate, the copy is not needed
        # as it is not a deep copy and sa_response_presentation is not used
        sa_response_presentation = sa_response.copy()

        if session["endpoint"] != "classify-v3":
            sa_response_presentation["categorisation"]["codings"] = (
                sa_response_presentation["categorisation"]["codings"][1:]
            )
        else:
            print("classify-v3 endpoint - retaining first candidate")

        print("SA_RESPONSE - - - -", sa_response)

        if (
            sa_response.get("categorisation")
            and sa_response["categorisation"].get("sic_code") is None
        ):
            # Take the first enrty from categorisation.codings.coding.code
            sic_code = sa_response["categorisation"]["codings"][0]["code"]
            sic_description = sa_response["categorisation"]["codings"][0][
                "code_description"
            ]
            print("SIC Code:", sic_code)
            print("SIC Description:", sic_description)
            sa_response["categorisation"]["sic_code"] = sic_code
            sa_response["categorisation"]["sic_description"] = sic_description
            # Remove the first ecntry from codings
            sa_response["categorisation"]["codings"] = sa_response["categorisation"][
                "codings"
            ][1:]

        # print("Filtered responses:", filtered_responses)
        html_output = render_classification_results(
            sa_response, filtered_responses, time_taken, survey_assist_time
        )

        sa_result = [
            {
                "interaction": "classification",
                "type": "sic",
                "title": "Initial SIC",
                "html_output": html_output,
            }
        ]

        print(
            "Updated organisation description:", org_description_question[0]["response"]
        )

        filtered_responses[2]["response"] = org_description_question[0]["response"]

        # Get the updated classification using the answers
        # to the follow up questions from the first interaction with Survey Assist
        updated_classification = get_classification(
            backend_api_url,
            session["endpoint"],
            jwt_token,
            "gemini",
            "sic",
            filtered_responses,
            logger,
        )

        # Add the updated classification to the session data
        save_classification_response(session, updated_classification)

        print("Updated classification:", updated_classification)

        updated_api_response = map_api_response_to_internal(updated_classification)

        if session["endpoint"] != "classify-v3":
            # Remove the first candidate from the classification
            updated_api_response["categorisation"]["codings"] = updated_api_response[
                "categorisation"
            ]["codings"][1:]
        else:
            logger.info("classify-v3 endpoint - retaining first candidate")
            # if codeable is False, set sic_code and description from the first candidate
            if not updated_api_response["categorisation"]["codeable"]:
                # Take the entry from categorisation.codings that has the highest confidence
                # first element has highest confidence
                sic_code = updated_api_response["categorisation"]["codings"][0]["code"]
                sic_description = updated_api_response["categorisation"]["codings"][0][
                    "code_description"
                ]
                logger.info(
                    f"Setting SIC code to {sic_code} and description to {sic_description}"
                )
                updated_api_response["categorisation"]["sic_code"] = sic_code
                updated_api_response["categorisation"][
                    "sic_description"
                ] = sic_description

        # TODO - need to store updated_api_response and sa_response
        # in the session data so they can be saved to the API

        # Render the updated classification results
        html_output = render_classification_results(
            updated_api_response, filtered_responses, time_taken, survey_assist_time
        )

        sa_result.insert(
            0,
            {
                "interaction": "classification",
                "type": "final-sic",
                "title": "Final - SIC",
                "html_output": html_output,
            },
        )

        if "sic_lookup" in session:
            sic_lookup_res = session.get("sic_lookup")
            lookup_result = create_lookup_result(sic_lookup_res)
            sa_result.append(lookup_result)

        return render_template("classification_template.html", sa_result=sa_result)
    else:
        if "sic_lookup" in session:
            sic_lookup_res = session.get("sic_lookup")
            lookup_result = create_lookup_result(sic_lookup_res)
            sa_result = [lookup_result]
            return render_template("siclookup_template.html", sa_result=sa_result)

        print("Session data not found")
        return redirect(url_for("thank_you", survey=SURVEY_NAME))


# Route to make an API request (used for testing)
# TODO - split into functions
@app.route("/save_results", methods=["GET", "POST"])
def save_results():  # noqa: PLR0911, PLR0915, C901

    survey_data = session.get("survey")

    time_dict = {
        "time_start": survey_data["survey"]["time_start"],
        "time_end": survey_data["survey"]["time_end"],
        "survey_assist_time_start": survey_data["survey"]["survey_assist_time_start"],
        "survey_assist_time_end": survey_data["survey"]["survey_assist_time_end"],
    }
    fields = [
        "time_start",
        "time_end",
        "survey_assist_time_start",
        "survey_assist_time_end",
    ]
    times = datetime_to_string(time_dict, fields)
    print("=====TIMES=====")
    print(times)
    print("================")

    user = session.get("user", "unknown.user")

    if user != "unknown.user":
        # Extract everything before @
        user = user.split("@")[0]

    print("========BODY========")
    print("user_id:", user)
    print("survey_name:", SURVEY_NAME)
    print("time_start:", times["time_start"])
    print("time_end:", times["time_end"])
    print("survey_assist_time_start:", times["survey_assist_time_start"])
    print("survey_assist_time_end:", times["survey_assist_time_end"])
    print("survey_schema - core questions", questions)
    print("survey_schema - survey assist", ai_assist)
    print("survey_response - questions", survey_data["survey"]["questions"])
    print("====================")

    # Get the sa_response from the session data
    sa_response = session.get("sa_response", [])

    sa_response_list = [
        {
            "type": "classification",
            "response": json.dumps(response),
            "interaction_sequence": index + 1,
        }
        for index, response in enumerate(sa_response)
    ]

    if "sic_lookup" in session:
        sic_lookup_response = session.get("sic_lookup")
        sic_lookup_result = format_lookup_response(sic_lookup_response)
        sa_response_list.append(sic_lookup_result)

    print("=====SA INTERACTIONS LIST=====")
    print(sa_response_list)
    print("==========================")

    api_url = backend_api_url + "/survey-assist/response"

    body = {
        "user_id": user,
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
                            "survey_assist": ai_assist,
                        },
                        "survey_response": {
                            "questions": survey_data["survey"]["questions"]
                        },
                    }
                ],
                "survey_assist": {"interactions": sa_response_list},
            }
        ],
    }

    headers = {"Authorization": f"Bearer {jwt_token}"}

    log_api_send(logger, api_url, body)
    # make an api request
    try:
        # Send a request to the Survey Assist API
        response = requests.post(
            api_url, json=body, headers=headers, timeout=API_TIMER_SEC
        )
        log_api_rcv(logger, api_url, response.json())

        if response.status_code != HTTPStatus.OK or not response.json():
            return redirect(url_for("error_page"))

        # Else update the saved result with the test notes
        # TODO - this is a temporary solution, needs integrating
        # with the API
        saved_response = get_last_survey_response(
            bucket_name=BUCKET_NAME, base_folder="TLFS_PoC", user=user
        )

        print(f"Saved response: {saved_response}")
        print("Saved response type:", type(saved_response))
        print(
            "Saved response Job Title:",
            saved_response["response"]["survey_response"]["questions"][1]["response"],
        )

        # Add the test notes to the saved response
        # These were not added when the results were saved to survey_assist (above)
        # as this is primarily for the test harness and not a part of the survey journey.
        notes = {
            "notes": [
                {
                    "code": request.form.get("expected-code"),
                    "text": request.form.get("test-notes"),
                }
            ]
        }

        update_last_survey_response(
            bucket_name=BUCKET_NAME, base_folder="TLFS_PoC", user=user, new_fields=notes
        )

        updated_response = get_last_survey_response(
            bucket_name=BUCKET_NAME, base_folder="TLFS_PoC", user=user
        )

        print(f"Updated response: {updated_response}")
        print(f"Updates response notes: {updated_response['notes']}")

        print("/save_results (exit)")
        if print_session_size() > SESSION_LIMIT:
            print_session()

        return render_template("thank_you.html", survey=SURVEY_NAME)

    except requests.exceptions.Timeout:
        print("Error: Request timed out")
        return redirect(url_for("error_page"))

    except requests.exceptions.ConnectionError:
        print("Error: Failed to connect to the API")
        return redirect(url_for("error_page"))

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        return redirect(url_for("error_page"))

    except requests.exceptions.RequestException as req_err:
        # Catch other requests-related errors
        print(f"Request error: {req_err}")
        return redirect(url_for("error_page"))

    except KeyError as key_err:
        print(f"Error: Missing expected data in response - {key_err}")
        return redirect(url_for("error_page"))

    except Exception as e:
        # General exception for unexpected errors
        print(f"Unexpected error occurred: {e}")
        return redirect(url_for("error_page"))


# The survey route summarises the data that has been
# entered by user, using the session data held in the survey
# dictionary. The data is then displayed in a summary template
@app.route("/summary")
def summary():
    print("/summary")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    survey_data = session.get("survey")
    survey_questions = survey_data["survey"]["questions"]

    # Print warning when time_start is not set
    if survey_data["survey"]["time_start"] is None:
        print("WARNING: Survey - time_start is not set")

    # Calculate the time_end based on the current timestamp
    survey_data["survey"]["time_end"] = datetime.now(timezone.utc)
    session.modified = True

    print(
        survey_data["survey"]["time_start"], survey_data["survey"]["time_start"].tzinfo
    )
    print(survey_data["survey"]["time_end"], survey_data["survey"]["time_end"].tzinfo)

    # Print the time taken in seconds to answer the survey
    time_taken = (
        survey_data["survey"]["time_end"] - survey_data["survey"]["time_start"]
    ).total_seconds()
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

    # Mark the survey assist time start
    user_survey.get("survey")["survey_assist_time_start"] = datetime.now(timezone.utc)
    session.modified = True

    if "PLACEHOLDER_FOLLOWUP" in ai_assist["consent"]["question_text"]:
        # Get the maximum followup
        max_followup = ai_assist["consent"]["max_followup"]

        if session["follow_up_type"] != "both":
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


# Rendered at the end of the survey
@app.route("/thank_you")
def thank_you():
    print_session()
    return render_template("thank_you.html", survey=SURVEY_NAME)


# Simple route to handle errors
# TODO - render error template
@app.route("/error")
def error_page():
    # get error parameter from the URL
    error = request.args.get("error")
    if error:
        safe_error = escape(error)
        return f"An error occurred: {safe_error}"
    return "An error occurred. Please try again later."


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


# --- Supporting functions below this point ---
def get_users():
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE)
        data = json.loads(blob.download_as_text())
        return data.get("users", [])
    except Exception as e:
        print(f"Error getting users: {e}")
    return []


def get_users_by_roles(*roles):
    """Filters users by the specified roles.
    Single role - get_users_by_roles("admin").
    Multiple roles - get_users_by_roles("admin", "tester").

    Args:
        *roles: Variable length argument list of roles to filter by.

    Returns:
        list: A list of user dictionaries matching the specified roles.
    """
    users = get_users()

    return [user["email"] for user in users if user["role"] in roles]


def get_user_role(email):
    """Validate the user against the credentials in the GCP bucket."""
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE)
        data = json.loads(blob.download_as_text())

        # Check if the user exists and the password matches
        for user in data.get("users", []):
            if user["email"] == email:
                return user["role"]
    except Exception as e:
        print(f"Error validating user: {e}")
    return False


def validate_user(email, password):
    """Validate the user against the credentials in the GCP bucket."""
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE)
        data = json.loads(blob.download_as_text())

        # Check if the user exists and the password matches
        for user in data.get("users", []):
            if user["email"] == email and user["password"] == password:
                return True
    except Exception as e:
        print(f"Error validating user: {e}")
    return False


@log_entry(logger)
def consent_skip():
    user_survey = session.get("survey")
    user_survey.get("survey")["survey_assist_time_end"] = datetime.now(timezone.utc)

    # If sa_response in in the session, remove it
    if "sa_response" in session:
        print("Removing sa_response from session")
        session.pop("sa_response")

    # Skip to next standard question
    session["current_question_index"] += 1
    session.modified = True
    return redirect(url_for("survey"))


# TODO - move to a separate file
@log_entry(logger)
def consent_redirect():
    print("/consent_redirect (entry)")
    if print_session_size() > SESSION_LIMIT:
        print_session()
    log_session(logger)
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

    print("/consent_redirect (exit)")
    if print_session_size() > SESSION_LIMIT:
        print_session()
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
@log_entry(logger)
def followup_redirect():
    print("followup_redirect (entry)")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    log_session(logger)
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
        if "follow_up" in session and session["follow_up_type"] == "both":
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
                        "response_options": mapped_question_data.get(
                            "response_options"
                        ),
                        "response": None,  # added after user input
                        "response_name": response_name,
                    }
                )
                session.modified = True

                print("followup_redirect (exit A)")
                if print_session_size() > SESSION_LIMIT:
                    print_session()

                return render_template(
                    "question_template.html", **mapped_question.to_dict()
                )

        # Mark the end time for the survey assist
        survey_data.get("survey")["survey_assist_time_end"] = datetime.now(timezone.utc)

        # increment the current question index to
        # get the next question
        session["current_question_index"] += 1
        session.modified = True

        print("followup_redirect (exit B)")
        if print_session_size() > SESSION_LIMIT:
            print_session()

        return redirect(url_for("survey"))


@log_entry(logger)
def sic_lookup(request, value):  # noqa: PLR0911
    # Send Get Request to the API
    api_url = (
        backend_api_url
        + f"/survey-assist/sic-lookup?description={request.form.get(value)}&similarity=true"
    )
    headers = {"Authorization": f"Bearer {jwt_token}"}
    log_api_send(logger, api_url, None)
    try:
        response = requests.get(api_url, headers=headers, timeout=API_TIMER_SEC)
        response_data = response.json()
        log_api_rcv(logger, api_url, response_data)
        return response_data
    except requests.exceptions.Timeout:
        return jsonify({"error": "The request timed out. Please try again later."}), 504
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {"error": "Failed to connect to the API. Please check your connection."}
            ),
            502,
        )
    except requests.exceptions.HTTPError as http_err:
        return (
            jsonify({"error": f"HTTP error occurred: {http_err.response.status_code}"}),
            500,
        )
    except ValueError:
        # For JSON decoding errors
        return jsonify({"error": "Failed to parse the response from the API."}), 500
    except KeyError as key_err:
        # This can be invalid JWT, check GCP logs
        return (
            jsonify(
                {"error": f"Missing expected data: {str(key_err)}"}  # noqa: RUF010
            ),
            500,
        )
    except Exception:
        return (
            jsonify({"error": "An unexpected error occurred. Please try again later."}),
            500,
        )


# Handles the redirect after a question has been answered.
# For interactions this will be to the survey_assist route
# For regular questions this will be to the survey route
@log_entry(logger)
def update_session_and_redirect(key, value, route):  # noqa: PLR0912, PLR0915, C901

    print("update_session_and_redirect (entry)")
    if print_session_size() > SESSION_LIMIT:
        print_session()
    log_session(logger)

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
            "used_for_classifications": current_question.get(
                "used_for_classifications"
            ),
        }
    )

    # If ai assist is enabled and the current question has an interaction
    # then redirect to the consent page to ask the user if they want to
    # continue with the AI assist interaction
    if ai_assist.get("enabled", True):
        consent = False

        session.modified = True
        interactions = ai_assist.get("interactions")
        if len(interactions) > 0 and current_question.get(
            "question_id"
        ) == interactions[0].get("after_question_id"):

            if ai_assist.get("sic_lookup", False):

                # Make request to lookup org description in SIC knowledge base
                lookup_resp = sic_lookup(request, value)

                if lookup_resp.get("error"):
                    return lookup_resp

                if lookup_resp.get("code"):
                    print("SIC Code found:", lookup_resp.get("code"))
                    if "sic_lookup" not in session:
                        session["sic_lookup"] = {
                            "org_description": request.form.get(value),
                            "sic_code": lookup_resp.get("code"),
                            "sic_code_meta": lookup_resp.get("code_meta"),
                            "sic_code_division_meta": lookup_resp.get(
                                "code_division_meta"
                            ),
                        }
                else:
                    # SIC code not found, check for potential matches
                    if "sic_lookup" not in session:
                        potential_codes = lookup_resp.get("potential_matches").get(
                            "codes", []
                        )[:5]
                        potential_descriptions = lookup_resp.get(
                            "potential_matches"
                        ).get("descriptions", [])[:5]
                        potential_divisions = lookup_resp.get("potential_matches").get(
                            "divisions", []
                        )[:5]

                        session["sic_lookup"] = {
                            "org_description": request.form.get(value),
                            "sic_code": None,
                            "sic_code_meta": None,
                            "sic_code_division_meta": None,
                            "potential_sic_codes_count": lookup_resp.get(
                                "potential_matches"
                            ).get("codes_count"),
                            "potential_sic_divisions_count": lookup_resp.get(
                                "potential_matches"
                            ).get("divisions_count"),
                            "potential_sic_codes": [
                                {"code": code, "description": desc}
                                for code, desc in zip(
                                    potential_codes, potential_descriptions
                                )
                            ],
                            "potential_sic_divisions": [
                                {
                                    "code": division.get("code"),
                                    "title": division.get("meta", {}).get("title"),
                                    "detail": "",
                                    # Session size exhausts if detail is included
                                    #  "detail": division.get("meta", {}).get("detail"),
                                }
                                for division in potential_divisions
                            ],
                        }

                    consent = True

                session.modified = True
            else:
                # SIC Lookup not enabled, but AI Assist is enabled
                # ask consent
                consent = True

            print("update_session_and_redirect (exit A)")
            if print_session_size() > SESSION_LIMIT:
                print_session()

            if consent:
                # print("AI Assist interaction detected - REDIRECTING to consent")
                return redirect(url_for("survey_assist_consent"))
            else:
                # SIC code found, skip Survey Assist consent
                print("SIC code found, skipping Survey Assist consent")
                return consent_skip()

    session["current_question_index"] += 1
    session.modified = True

    print("update_session_and_redirect (exit B)")
    if print_session_size() > SESSION_LIMIT:
        print_session()

    return redirect(url_for(route))
