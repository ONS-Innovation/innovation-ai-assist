# survey_data = {
#     "questions": [
#       {
#         "question_id": "q1",
#         "question_name": "paid_job_question",
#         "title": "Paid Job",
#         "question_text": "Did you have a paid job, either as an employee or self-employed, in the week 04 November to 11 November 2024?",
#         "question_description": "",
#         "response_type": "radio",
#         "response_name": "paid-job",
#         "response_options": [
#           { "id": "paid-job-yes", "label": {"text": "Yes"}, "value": "yes" },
#           { "id": "paid-job-no", "label": {"text": "No"}, "value": "no" }
#         ],
#         "justification_text": "Placeholder text",
#         "placeholder_field": "",
#         "button_text": "Save and continue",
#         "used_for_classifications": []
#       },
#       {
#         "question_id": "q2",
#         "question_name": "job_title_question",
#         "title": "Job Title",
#         "question_text": "What is your exact job title for your main job or business?",
#         "question_description": "",
#         "response_type": "text",
#         "response_name": "job-title",
#         "response_options": [],
#         "justification_text": "<p>Placeholder text</p>",
#         "placeholder_field": "",
#         "button_text": "Save and continue",
#         "used_for_classifications": ["sic","soc"]
#       },
#       {
#         "question_id": "q3",
#         "question_name": "job_description_question",
#         "title": "Job Description",
#         "question_text": "Describe what you do in that job or business as a PLACEHOLDER_TEXT",
#         "question_description": "<p>For example, I pack crates of goods in a warehouse for a supermarket chain</p>",
#         "response_type": "text",
#         "response_name": "job-description",
#         "response_options": [],
#         "justification_text": "<p>Placeholder text</p>",
#         "button_text": "Save and continue",
#         "placeholder_field": "job_title",
#         "used_for_classifications": ["sic","soc"]
#       },
#       {
#         "question_id": "q4",
#         "question_name": "organisation_activity_question",
#         "title": "Organisation Activity",
#         "question_text": "At your main job, describe the main activity of the business or organisation",
#         "question_description": "<p>For example, elderly residential care, food and beverage manufacturing or primary education</p>",
#         "response_type": "text",
#         "response_name": "organisation-activity",
#         "response_options": [],
#         "justification_text": "<p>Placeholder text</p>",
#         "placeholder_field": "",
#         "button_text": "Save and continue",
#         "used_for_classifications": ["sic","soc"]
#       },
#       {
#         "question_id": "q5",
#         "question_name": "organisation_type_question",
#         "title": "Organisation Type",
#         "question_text": "What kind of organisation was it?",
#         "question_description": "",
#         "response_type": "radio",
#         "response_name": "organisation-type",
#         "response_options": [
#           { "id": "limited-company", "label": {"text": "A public limited company"}, "value": "A public limited company" },
#           { "id": "nationalised-industry", "label": {"text": "A nationalised industry or state corporation"}, "value": "A nationalised industry or state corporation" },
#           { "id": "central-government", "label": {"text": "Central government or civil service"}, "value": "Central government or civil service" },
#           { "id": "local-government", "label": {"text": "Local government or council (including fire service and local authority controlled schools or colleges)"}, "value": "Local government or council (including fire service and local authority controlled schools or colleges)" },
#           { "id": "university-grant-funded", "label": {"text": "A university or other grant funded establishment (including opted-out schools)"}, "value": "A university or other grant funded establishment (including opted-out schools)" },
#           { "id": "health-authority", "label": {"text": "A health authority or NHS Trust"}, "value": "A health authority or NHS Trust" },
#           { "id": "charity-volunteer", "label": {"text": "A charity, voluntary organisation or trust"}, "value": "A charity, voluntary organisation or trust" },
#           { "id": "armed-forces", "label": {"text": "The armed forces"}, "value": "The armed forces" },
#           { "id": "other-organisation", "label": {"text": "Some other kind of organisation"}, "value": "Some other kind of organisation" }
#         ],
#         "justification_text": "<p>Placeholder text</p>",
#         "placeholder_field": "",
#         "button_text": "Save and continue",
#         "used_for_classifications": []
#       }    
#     ],
#     "ai_assist": {
#       "enabled": True,
#       "question_assist_label": "<br>(Asked by Survey Assist)</br>",
#       "consent": {
#         "required": True,
#         "question_id": "c1",
#         "title": "Survey Assist Consent",
#         "question_name":"survey_assist_consent",
#         "question_text": "Can Survey Assist ask PLACEHOLDER_FOLLOWUP to better understand PLACEHOLDER_REASON?",
#         "justification_text": "<p>Survey Assist generates intelligent follow up questions based on the answers you have given so far to help ONS to better understand your main job or the organisation you work for. ONS asks for your consent as Survey Assist uses artifical intelligence to pose questions that enable us to better understand your survey responses.</p>",
#         "placeholder_reason": "your main job and workplace",
#         "max_followup": 3
#       },
#       "interactions": [
#         {
#           "after_question_id": "q4",
#           "type": "classification",
#           "param": "sic",
#           "follow_up": {
#             "allowed": True,
#             "presentation": {
#                "immediate": True,
#                "after_question_id": ""
#             }
#           }
#         }
#       ]
#     }
#   }

# response_data = {  # Simplified example structure
#     "survey": {
#         "questions": [
#             {
#                 "question_id": "q1",
#                 "question_text": "Did you have a paid job, either as an employee or self-employed, in the week 04 November to 11 November 2024?",
#                 "response": "yes"
#             },
#             {
#                 "question_id": "q2",
#                 "question_text": "What is your exact job title for your main job or business?",
#                 "response": "teacher"
#             },
#             {
#                 "question_id": "q3",
#                 "question_text": "Describe what you do in that job or business as a teacher",
#                 "response": "teach maths"
#             },
#             {
#                 "question_id": "q4",
#                 "question_text": "At your main job, describe the main activity of the business or organisation",
#                 "response": "education"
#             },
#             {
#                 "question_id": "q5",
#                 "question_text": "What kind of organisation was it?",
#                 "response": "A public limited company"
#             }
#         ]
#     }
# }


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
        {
            "question_text": question["question_text"],
            "response": question["response"]
        }
        for question in survey_questions
        if question["question_id"] in classified_questions
    ]

    return filtered_responses


# classification_type = "sic"
# classification_questions = get_questions_by_classification(survey_data, classification_type)
# print(classification_questions)

# filtered_responses = filter_classification_responses(response_data, classification_questions)
# print(filtered_responses)
