from jinja2 import Template
from datetime import datetime, timezone


def datetime_to_string(data, fields, format="%Y-%m-%d %H:%M:%S %Z"):
    """Converts specified datetime fields in a dictionary to strings.

    :param data: The dictionary containing the datetime fields.
    :param fields: A list of keys to convert to strings.
    :param format: The string format for the datetime (default includes timezone).
    :return: The updated dictionary with datetime fields as strings.
    """
    for field in fields:
        if field in data and isinstance(data[field], datetime):
            data[field] = data[field].strftime(format)
    return data


def string_to_datetime(data, fields, format="%Y-%m-%d %H:%M:%S %Z"):
    """Converts specified string fields in a dictionary back to datetime objects.

    :param data: The dictionary containing the string fields.
    :param fields: A list of keys to convert to datetime objects.
    :param format: The string format of the datetime (default includes timezone).
    :return: The updated dictionary with string fields as datetime objects.
    """
    for field in fields:
        if field in data and isinstance(data[field], str):
            data[field] = datetime.strptime(data[field], format)
    return data


# Function to render the classification results from Survey Assist
# This function will render the classification results in an HTML format
def render_classification_results(response_data,
                                  question_responses,
                                  survey_time,
                                  survey_assist_time):

    question_response_dict = {
        question["question_text"]: question["response"]
        for question in question_responses
    }
    print("Question Response Dict:", question_response_dict)

    template = """
    <h2>Classification Results</h2>
    <h3>Most Likely</h3>
    <ul><li>{{ categorisation.sic_code }} - {{ categorisation.sic_description }}</li></ul>
    <br>

    <h3>Alternatives</h3>
    <ul>
    {% for coding in categorisation.codings %}
        <li>{{ coding.code }} - {{ coding.code_description }}</li>
    {% endfor %}
    </ul>
    <br>

    <h3>Justification</h3>
    <p>{{ categorisation.justification }}</p>
    <br>

    <h3>Input for Classification</h3>
    {% for question, answer in question_responses.items() %}
    <strong>{{ question }}</strong>
    <p>{{ answer }}</p>
    {% endfor %}
    <br>

    <h3>Survey Timings</h3>
    <p>Total time in seconds: {{ survey_time }}</p>
    <p>Survey Assist interaction time in seconds: {{ survey_assist_time }}</p>
    """

    # Render the template with the response data and question responses
    jinja_template = Template(template)
    rendered_html = jinja_template.render(
        categorisation=response_data.get("categorisation", {}),
        question_responses=question_response_dict,
        survey_time=survey_time,
        survey_assist_time=survey_assist_time
    )

    return rendered_html
