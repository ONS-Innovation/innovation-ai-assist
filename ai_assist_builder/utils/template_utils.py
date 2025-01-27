from datetime import datetime

from jinja2 import Environment, select_autoescape


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
def render_classification_results(
    response_data, question_responses, survey_time, survey_assist_time
):

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
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    jinja_template = env.from_string(template)
    rendered_html = jinja_template.render(
        categorisation=response_data.get("categorisation", {}),
        question_responses=question_response_dict,
        survey_time=survey_time,
        survey_assist_time=survey_assist_time,
    )

    return rendered_html


def render_sic_lookup_unsuccessful(
    org_description,
    sic_code_count,
    sic_code_division_count,
    potential_sic_codes,
    potential_sic_divisions,
):

    template = """
    <h2>SIC Lookup Failed</h2>
    <h3>Organisation Description</h3>
    <p><strong>{{ org_description }}</strong></p>
    <p>No SIC code found for the organisation description provided.</p>

    <h3>{{sic_code_count}} - Possible SIC Codes Found</h3>

    {% if potential_sic_codes %}
    <p>A sample of at most 5 potential SIC codes</p>
    {% for item in potential_sic_codes %}
    <p>{{ item.code }} - {{item.description}}</p>
    {% endfor %}
    {% else %}
    <p>No potential SIC codes found</p>
    {% endif %}
    <h3>{{sic_code_division_count}} - Possible SIC Divisions Found</h3>

    {% if potential_sic_divisions %}
    <p>A sample of at most 5 potential SIC divisions</p>
    {% for division in potential_sic_divisions %}
    <p>{{ division.code }} - {{division.title}}</p>
    {% endfor %}
    {% else %}
    <p>No potential SIC divisions found</p>
    {% endif %}
    """

    # Render the template with the response data and question responses
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    jinja_template = env.from_string(template)
    rendered_html = jinja_template.render(
        org_description=org_description,
        sic_code_count=sic_code_count,
        sic_code_division_count=sic_code_division_count,
        potential_sic_codes=potential_sic_codes,
        potential_sic_divisions=potential_sic_divisions,
    )

    return rendered_html


# Function to render the classification results from Survey Assist
# This function will render the classification results in an HTML format
def render_sic_lookup_results(
    org_description, sic_code, sic_code_meta, sic_code_division_meta
):

    template = """
    <h2>SIC Found</h2>
    <h3>Organisation Description</h3>
    <p><strong>{{ org_description }}</strong></p>

    <h3>{{ sic_code }}</strong> - {{ sic_code_meta.title }}</h3>

    {% if sic_code_meta.detail %}
    <p>{{ sic_code_meta.detail }}</p>
    {% else %}
    <p>No description available</p>
    {% endif %}

    {% if sic_code_meta.includes %}
    <h3>Includes</h3>
    {% for include in sic_code_meta.includes %}
    <p>{{ include }}</p>
    {% endfor %}
    {% endif %}

    {% if sic_code_meta.excludes %}
    <h3>Excludes</h3>
    {% for exclude in sic_code_meta.excludes %}
    <p>{{ exclude }}</p>
    {% endfor %}
    {% endif %}

    <h3>Highest Level Code Division</h3>
    <p><strong>{{sic_code_division_meta.code}}</strong> - {{sic_code_division_meta.title}}</p>

    {% if sic_code_division_meta.detail %}
    <p>{{ sic_code_division_meta.detail }}</p>
    {% else %}
    <p>No description available</p>
    {% endif %}

    {% if sic_code_division_meta.includes %}
    <h4>Includes</h4>
    {% for include in sic_code_division_meta.includes %}
    <p>{{ include }}</p>
    {% endfor %}
    {% endif %}

    {% if sic_code_division_meta.excludes %}
    <h4>Excludes</h4>
    {% for exclude in sic_code_division_meta.excludes %}
    <p>{{ exclude }}</p>
    {% endfor %}
    {% endif %}
    """

    # Render the template with the response data and question responses
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    jinja_template = env.from_string(template)
    rendered_html = jinja_template.render(
        org_description=org_description,
        sic_code=sic_code,
        sic_code_meta=sic_code_meta,
        sic_code_division_meta=sic_code_division_meta,
    )

    return rendered_html
