# This function maps the API response to the internal representation of the Survey Assist model
def map_api_response_to_internal(api_response: dict) -> list:
    def create_follow_up_question(
        api_response: dict, id: str, response_type: str, select_options: list
    ) -> dict:
        if response_type == "confirm":
            question_text = f"Does '{select_options[0]}' describe your organisation?"
            select_options[0] = "Yes"
            response_type = "select"
        else:
            question_text = (
                api_response.get("followup", "")
                if response_type == "text"
                else "Which of these best describes your organisation's activities?"
            )

        return {
            "follow_up_id": id,
            "question_text": question_text,
            "question_name": "ai_assist_followup",
            "response_type": response_type,
            "select_options": select_options,
        }

    # Map SIC candidates to internal codings format
    codings = [
        {
            "code": candidate["sic_code"],
            "code_description": candidate["sic_descriptive"],
            "confidence": candidate["likelihood"],
        }
        for candidate in api_response.get("sic_candidates", [])
    ]

    internal_representation = {
        "categorisation": {
            "codeable": api_response.get("classified", False),
            "codings": codings,
            "sic_code": api_response.get("sic_code", ""),
            "sic_description": api_response.get("sic_description", ""),
            "justification": api_response.get("reasoning", ""),
        },
        "follow_up": {"questions": []},
    }

    if not api_response.get("classified", False):
        # There is a choice of classifications, create follow-up question
        # list which will be a text based question and a select based question
        if api_response.get("followup"):
            follow_up = internal_representation["follow_up"]
            follow_up["questions"].append(
                create_follow_up_question(api_response, "f1.1", "text", [])
            )

        # Create select follow-up question
        if api_response.get("sic_candidates"):
            select_options = [
                candidate["sic_descriptive"]
                for candidate in api_response["sic_candidates"]
            ]
            select_options.append("None of the above")
            follow_up = internal_representation["follow_up"]
            follow_up["questions"].append(
                create_follow_up_question(
                    api_response, "f1.2", "select", select_options
                )
            )
    else:
        # V3 classify can return classified == True when it
        # is confident a sic mapping has been found
        # In this case, we want to confirm the mapping by asking the user
        # if they agree with organisation classification description
        follow_up = internal_representation["follow_up"]
        print("MAP Followup:", api_response.get("sic_description"))
        follow_up["questions"].append(
            create_follow_up_question(
                api_response,
                "f1.1",
                "confirm",
                [api_response.get("sic_description"), "No"],
            )
        )

    return internal_representation
