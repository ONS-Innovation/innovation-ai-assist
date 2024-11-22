class Question:
    def __init__(
        self,
        question_id,
        question_name,
        question_title,
        question_text,
        response_type,
        response_options,
    ):
        self.question_id = question_id
        self.question_name = question_name
        self.title = question_title
        self.question_text = question_text
        self.question_description = ""
        self.response_type = "radio" if response_type == "select" else response_type
        self.response_name = f"resp-{question_name.replace('_', '-')}"
        self.response_options = self.format_response_options(response_options)
        self.justification_text = "<p>Placeholder text</p>"
        self.placeholder_field = ""
        self.button_text = "Save and continue"

    @staticmethod
    def format_response_options(response_options):
        # Format the select options into the required response_options structure
        formatted_options = []
        for option in response_options:
            formatted_options.append(
                {
                    "id": f"{option["id"].lower().replace(' ', '-')}",
                    "label": option["label"],
                    "value": option["value"].lower(),
                }
            )
        return formatted_options

    def to_dict(self):
        # Return the question instance as a dictionary
        return {
            "question_id": self.question_id,
            "question_name": self.question_name,
            "title": self.title,
            "question_text": self.question_text,
            "question_description": self.question_description,
            "response_type": self.response_type,
            "response_name": self.response_name,
            "response_options": self.response_options,
            "justification_text": self.justification_text,
            "placeholder_field": self.placeholder_field,
            "button_text": self.button_text,
        }
