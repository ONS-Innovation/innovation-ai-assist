import datetime
import json

import requests
from flask import jsonify
from google.cloud import storage

# TODO - move this to central config
API_TIMER_SEC = 15


def get_questions_by_classification(survey_data, classification_type):
    """Filters questions from the survey based on the classification type in used_for_classifications.

    Args:
        survey_data (dict): The JSON structure of the survey.
        classification_type (str): The classification type to filter by (e.g., "sic").

    Returns:
        dict: A dictionary of question_id and question_text for matching questions.
    """
    # Extract the questions list
    questions = survey_data.get("questions", [])

    # Create a dictionary of matching questions
    filtered_questions = {
        question["question_id"]: question["question_text"]
        for question in questions
        if classification_type in question.get("used_for_classifications", [])
    }

    return filtered_questions


def filter_classification_responses(survey_data, classified_questions):
    """Filters survey responses based on classified questions.

    Args:
        survey_data (dict): The survey data containing questions and responses.
        classified_questions (dict): A dictionary of question_id and question_text
                                      from get_questions_by_classification.

    Returns:
        list: A list of dictionaries containing question_text and response.
    """
    # Extract the list of questions from the survey data
    survey_questions = survey_data.get("survey", {}).get("questions", [])

    # Filter the questions based on the classified_questions keys (question_ids)
    filtered_responses = [
        {"question_text": question["question_text"], "response": question["response"]}
        for question in survey_questions
        if question["question_id"] in classified_questions
    ]

    return filtered_responses


def get_classification(backend_api_url, jwt_token, llm, type, input_data):
    """Send a request to the Survey Assist API to classify the input data.

    Args:
        backend_api_url (str): The URL of the Survey Assist API.
        jwt_token (str): The JWT token for authentication.
        llm (str): The LLM code for the classification.
        type (str): The type of classification (e.g., "sic").
        input_data (list): A list of dictionaries containing the input data.

    Returns:
        response_data (dict): The response data from the API.
    """
    api_url = backend_api_url + "/survey-assist/classify"
    print("SENDING REQUEST API URL:", api_url)
    body = {
        "llm": llm,
        "type": type,
        "job_title": input_data[0]["response"],
        "job_description": input_data[1]["response"],
        "org_description": input_data[2]["response"],
    }

    headers = {"Authorization": f"Bearer {jwt_token}"}

    try:
        # Send a request to the Survey Assist API
        response = requests.post(
            api_url, json=body, headers=headers, timeout=API_TIMER_SEC
        )
        response_data = response.json()

        return response_data
    except Exception as e:
        print("Error occurred getting classification:", e)
        # Handle errors and return an appropriate message
        return jsonify({"error": str(e)}), 500


def save_classification_response(session, response):
    """Save the classification data to the session.

    Args:
        session (dict): The session data.
        response (dict): The classification data to save.
    """
    if "sa_response" not in session:
        session["sa_response"] = []  # Initialize as an empty list

    # Append the new API response
    session["sa_response"].append(response)

    # Save the updated session data
    session.modified = True  # Ensure Flask saves the changes


# Function to send a user note to the recorded results
# TODO_ This is a temporary function to demonstrate saving user notes
def get_last_survey_response(bucket_name, base_folder, user):
    # Initialize the storage client
    storage_client = storage.Client()

    # Get the bucket
    bucket = storage_client.bucket(bucket_name)

    # Build the file path based on user email and today's date
    today = datetime.datetime.now().strftime("%d-%m-%Y")
    file_path = f"{base_folder}/{user}/{today}_results.json"

    # Check if the file exists in the bucket
    blob = bucket.blob(file_path)
    if not blob.exists():
        print(f"File {file_path} does not exist in bucket {bucket_name}.")
        return None

    # Download and parse the JSON file
    file_content = blob.download_as_text()
    data = json.loads(file_content)

    # Check for survey_responses and retrieve the last response
    survey_responses = data.get("survey_responses", [])
    if not survey_responses:
        print("No survey responses found in the file.")
        return None

    # Return the last survey response
    last_response = survey_responses[-1]
    return last_response


def update_last_survey_response(bucket_name, base_folder, user, new_fields):
    # Initialize the storage client
    storage_client = storage.Client()

    # Get the bucket
    bucket = storage_client.bucket(bucket_name)

    # Build the file path based on user email and today's date
    today = datetime.datetime.now().strftime("%d-%m-%Y")
    file_path = f"{base_folder}/{user}/{today}_results.json"

    # Check if the file exists in the bucket
    blob = bucket.blob(file_path)
    if not blob.exists():
        print(f"File {file_path} does not exist in bucket {bucket_name}.")
        return False

    # Download and parse the JSON file
    file_content = blob.download_as_text()
    data = json.loads(file_content)

    # Check for survey_responses and retrieve the last response
    survey_responses = data.get("survey_responses", [])
    if not survey_responses:
        print("No survey responses found in the file.")
        return False

    # Update the last survey response with the new fields
    last_response = survey_responses[-1]
    last_response.update(new_fields)

    # Save the updated last response back into the array
    survey_responses[-1] = last_response
    data["survey_responses"] = survey_responses

    # Upload the updated JSON file back to GCS
    updated_content = json.dumps(data, indent=2)
    blob.upload_from_string(updated_content, content_type="application/json")

    print(f"File {file_path} successfully updated in bucket {bucket_name}.")
    return True
