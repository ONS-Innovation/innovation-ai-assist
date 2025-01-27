import json  # noqa: I001
import os
import re
from datetime import datetime, timedelta

import pandas as pd
from flask import Response
from google.cloud import storage

from ai_assist_builder.models.results import Times  # noqa: I001, RUF100
from ai_assist_builder.models.results import (
    Candidate,
    Classification,
    Note,
    QuestionInteraction,
    Result,
)


def calculate_times(data):
    # Helper function to parse datetime and handle missing values
    def parse_time(time_str):
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S %Z")
        except (ValueError, TypeError):
            return None

    # Parse the times from the dictionary
    time_start = parse_time(data.get("time_start"))
    time_end = parse_time(data.get("time_end"))
    assist_start = parse_time(data.get("survey_assist_time_start"))
    assist_end = parse_time(data.get("survey_assist_time_end"))

    # Calculate total_time_secs
    if time_start and time_end:  # noqa: SIM108
        total_time_secs = int((time_end - time_start).total_seconds())
    else:
        total_time_secs = -1

    # Calculate interaction_time_secs
    if assist_start and assist_end:  # noqa: SIM108
        interaction_time_secs = int((assist_end - assist_start).total_seconds())
    else:
        # SIC Lookup was successful and survey assist was not used for initial and final classification
        interaction_time_secs = 0

    return {
        "total_time_secs": total_time_secs,
        "interaction_time_secs": interaction_time_secs,
    }


def create_test_id(time_start, user, job_title):
    # Parse the datetime string to extract the date and time in seconds
    try:
        start_datetime = datetime.strptime(time_start, "%Y-%m-%d %H:%M:%S %Z")
        formatted_date = start_datetime.strftime("%d%m%Y")
        start_time_hhmmss = start_datetime.strftime("%H%M%S")
    except ValueError:
        raise ValueError(  # noqa: B904
            "Invalid time_start format. Expected format: YYYY-MM-DD HH:MM:SS UTC"
        )

    # Process user and job_title by removing special characters and spaces
    user_cleaned = user.replace(".", "").replace(" ", "").lower()
    # Remove all non-alphanumeric characters from job_title and convert to lowercase
    job_title_cleaned = re.sub(r"[^a-zA-Z0-9]", "", job_title.lower())

    # Construct the test ID
    test_id = f"{user_cleaned}-{formatted_date}-{start_time_hhmmss}-{job_title_cleaned}"

    return test_id


# This function takes the stored data from test runs and parses it into a simpler format
# for easier analysis and comparison.
# result = {
#     "id": "",  # test ID
#     "type": "",  # classification type
#     "questions": [],
#     "interactions": [],
#     "classification": {
#         "initial": {
#             "ml_code": "",
#             "ml_description": "",
#             "ml_confidence": 0.0,
#             "candidates": [],
#             "justification": ""
#         },
#         "final": {
#             "ml_code": "",
#             "ml_description": "",
#             "ml_confidence": 0.0,
#             "candidates": [],
#             "justification": ""
#         }
#     },
#     "times": {
#         "total_time_secs": 0,
#         "interaction_time_secs": 0
#     },
#     "notes": []  # list of notes objects (text, expected_code)
# }
# results = [result1, result2, ...]
#
# TODO - simplify this function
def process_survey_responses(  # noqa: C901, PLR0912, PLR0915
    bucket_name, base_folder, user, date
):
    # Initialize the storage client
    storage_client = storage.Client()

    # Build the file path
    file_path = f"{base_folder}/{user}/{date}_results.json"

    # Get the bucket and blob
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_path)

    # Check if the file exists
    if not blob.exists():
        print(f"File {file_path} does not exist in bucket {bucket_name}.")
        return

    # Download and parse the JSON file
    file_content = blob.download_as_text()
    data = json.loads(file_content)

    # Access survey_responses
    survey_responses = data.get("survey_responses", [])

    if not survey_responses:
        print("No survey responses found.")
        return

    results = []

    # Process each survey response
    for entry in survey_responses:
        response = entry.get("response")
        time_start = response.get("time_start", "N/A")

        # Access survey_response
        survey_response = response.get("survey_response", {})
        questions = survey_response.get("questions", [])

        options = ""
        job_title = "unknownjobtitle"
        questions_results = []
        interactions_results = []
        initial_candidates = []
        final_candidates = []
        # Process each question
        for question in questions:
            # Check if "sic" is in used_for_classifications
            used_for_classifications = question.get("used_for_classifications", [])
            if "sic" in used_for_classifications:
                question_text = question.get("question_text")
                user_response = question.get("response")

                # Add the question and response to the list
                questions_results.append(
                    QuestionInteraction(text=question_text, response=user_response)
                )
            elif question.get("response_name") == "resp-ai-assist-followup":
                question_text = question.get("question_text")
                user_response = question.get("response")

                if question_text.startswith(
                    "Which of these best describes your organisation's activities?"
                ):
                    for option in question.get("response_options"):
                        options += option.get("value") + ", "
                    # Remove the last comma and space
                    options = options[:-2]
                    question_text = question_text.partition("?")[0] + "? " + options

                question_text = question_text.partition("<br><strong>(Asked")[0]

                # Add the question and response to the list
                interactions_results.append(
                    QuestionInteraction(text=question_text, response=user_response)
                )

            if question.get("response_name") == "job-title":
                job_title = question.get("response")

        survey_assist = entry.get("survey_assist", {})
        interactions = survey_assist.get("interactions", [])
        notes = entry.get("notes", "")
        initial_classification = None
        final_classification = None

        sic_lookup_data = {
            "sic_found": None,
            "sic_lookup_string": "N/A",
            "sic_lookup_response": {},
        }

        # Process each interaction
        for interaction in interactions:
            type = interaction.get("type")
            if type == "classification":
                sequence = interaction.get("interaction_sequence")

                # TODO - classification results are stored differently between first
                # interaction and final interaction.  For now, need to handle both cases.
                if sequence == 1:
                    categorisation = interaction.get("response", {}).get(
                        "categorisation", {}
                    )
                    justification = categorisation.get("justification", "")

                    candidates = categorisation.get("codings", [])

                    # most likely confidence needs to be caculated from the confidence of the first element
                    # of the list plus 0.1
                    if candidates:
                        ml_confidence = round(
                            candidates[0].get("confidence", 0.0) + 0.1, 1
                        )

                    # Add the most likely SIC code to first element of the list
                    candidates.insert(
                        0,
                        {
                            "confidence": categorisation.get(
                                "confidence", ml_confidence
                            ),
                            "code": categorisation.get("sic_code", "N/A"),
                            "code_description": categorisation.get(
                                "sic_description", "N/A"
                            ),
                        },
                    )

                    for candidate in candidates:
                        initial_candidates.append(
                            Candidate(
                                confidence=candidate.get("confidence", 0.0),
                                code=candidate.get("code", "N/A"),
                                description=candidate.get("code_description", "N/A"),
                            )
                        )

                    # Add the classification to the initial classification
                    initial_classification = Classification(
                        ml_code=categorisation.get("sic_code", "N/A"),
                        ml_description=categorisation.get("sic_description", "N/A"),
                        ml_confidence=ml_confidence,
                        candidates=initial_candidates,
                        justification=justification,
                    )
                else:
                    categorisation = interaction.get("response", {})
                    justification = categorisation.get("reasoning", "")
                    candidates = categorisation.get("sic_candidates", [])

                    if candidates:
                        ml_confidence = candidates[0].get("likelihood", 0.0)

                    for candidate in candidates:
                        conf = candidate.get("likelihood", 0.0)
                        final_candidates.append(
                            Candidate(
                                confidence=conf,
                                code=candidate.get("sic_code", "N/A"),
                                description=candidate.get("sic_descriptive", "N/A"),
                            )
                        )

                    # Add the classification to the final classification
                    final_classification = Classification(
                        ml_code=categorisation.get("sic_code", "N/A"),
                        ml_description=categorisation.get("sic_description", "N/A"),
                        ml_confidence=ml_confidence,
                        candidates=final_candidates,
                        justification=justification,
                    )
            elif (
                type == "sic"
            ):  # TODO - type of sic isn't really appropriate, want lookup-sic
                sic_lookup_resp = interaction.get("response", {})
                sic_found = interaction.get("found", False)
                sic_lookup_string = interaction.get("lookup_string", "N/A")

                # Add the lookup data to the result
                sic_lookup_data = {
                    "sic_found": sic_found,
                    "sic_lookup_string": sic_lookup_string,
                    "sic_lookup_response": sic_lookup_resp,
                }

        # Calculate times
        times = calculate_times(response)

        # Calculate the test ID
        test_id = create_test_id(time_start, user, job_title)

        # Create the result object
        result = Result(
            id=test_id,
            type="sic",
            questions=questions_results,
            interactions=interactions_results,
            classification={
                "initial": initial_classification,
                "final": final_classification,
            },
            sic_lookup=sic_lookup_data,
            times=Times(
                total_time_secs=times["total_time_secs"],
                interaction_time_secs=times["interaction_time_secs"],
            ),
            notes=[
                Note(text=note.get("text"), expected_code=note.get("code"))
                for note in notes
            ],
        )
        results.append(result)
    return results


def print_test_results(results, detailed=False):
    total_tests = len(results)
    pass_count = 0
    fail_count = 0
    na_count = 0

    for result in results:
        test_id = result.id
        job_title = result.questions[0].response if result.questions else "N/A"
        expected_sic = result.notes[0].expected_code if result.notes else "N/A"
        if expected_sic == "":
            expected_sic = "N/A"

        final_sic = result.classification["final"].ml_code
        initial_sic = result.classification["initial"].ml_code
        final_justification = result.classification["final"].justification
        initial_justification = result.classification["initial"].justification
        test_notes = result.notes[0].text if result.notes else "N/A"
        times = result.times
        result_status = (
            "N/A"
            if expected_sic == "N/A"
            else ("Pass" if expected_sic == final_sic else "Fail")
        )

        if result_status == "Pass":
            pass_count += 1
        elif result_status == "Fail":
            fail_count += 1
        else:
            na_count += 1

        # Print basic result information
        print("-----")
        print(f"Test ID: {test_id}")
        print(f"Job Title: {job_title}")
        print(f"Expected SIC: {expected_sic}")
        print(f"Final Most Likely SIC: {final_sic}")
        print(f"Initial Most Likely SIC: {initial_sic}")

        # If detailed is True, print additional information
        if detailed:
            print(
                f"Final SIC Confidence: {result.classification['final'].ml_confidence}"
            )
            # Print all final candidates with incremented index
            for x, candidate in enumerate(result.classification["final"].candidates, 1):
                print(f"Final Alternative SIC {x}: {candidate.code}")
                print(f"Final Alternative SIC confidence {x}: {candidate.confidence}")

            print(f"Final Justification: {final_justification}")

            print(
                f"Initial SIC Confidence: {result.classification['initial'].ml_confidence}"
            )
            # Print all initial candidates with incremented index
            for x, candidate in enumerate(
                result.classification["initial"].candidates, 1
            ):
                print(f"Initial Alternative SIC {x}: {candidate.code}")
                print(f"Initial Alternative SIC confidence {x}: {candidate.confidence}")

            print(f"Initial Justification: {initial_justification}")
            print(f"Total Time (secs): {times.total_time_secs}")
            print(f"Interaction Time (secs): {times.interaction_time_secs}")

        print(f"Test Notes: {test_notes}")
        print(f"Result: {result_status}")

        print("-----\n")

    # Print the summary
    print("===== TEST RESULTS SUMMARY =====")
    print(f"Total tests: {total_tests}")
    print(f"Pass: {pass_count}")
    print(f"Fail: {fail_count}")
    print(f"N/A: {na_count}")
    print("================================")


def generate_date_range(start_date_str):
    """Generate a list of dates from the start date to today's date (inclusive)."""
    start_date = datetime.strptime(start_date_str, "%d-%m-%Y")
    end_date = datetime.today()
    date_range = []

    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date.strftime("%d-%m-%Y"))
        current_date += timedelta(days=1)

    return date_range


def process_users(bucket_name, base_folder, users, start_date):
    """Process survey responses for a list of users and a given start date."""
    all_results = []

    # Generate date range from the start date to today
    date_range = generate_date_range(start_date)

    for user in users:
        for date in date_range:
            print(f"Processing responses for user: {user} on date: {date}")
            results = process_survey_responses(
                bucket_name=bucket_name, base_folder=base_folder, user=user, date=date
            )
            if results:
                all_results.extend(results)

    return all_results


def filter_and_write_csv(df, csv_path, drop_columns=False):
    # Identify columns matching the patterns
    columns_to_check = ["Question", "Response", "Interaction", "Interaction_Response"]
    threshold_map = {
        "Question": 4,
        "Response": 4,
        "Interaction": 3,
        "Interaction_Response": 3,
    }

    # Build regex pattern
    regex_patterns = [rf"{col}_\d+" for col in columns_to_check]

    columns_to_drop = []
    for col in df.columns:
        for pattern, prefix in zip(regex_patterns, columns_to_check):
            if re.match(pattern, col):
                # Extract the number part to check the threshold
                num = int(col.split("_")[-1])
                if num >= threshold_map[prefix]:
                    columns_to_drop.append(col)

    # Display identified columns
    print("Columns identified for potential drop:")
    print(columns_to_drop)

    if drop_columns:
        df = df.drop(columns=columns_to_drop)
        print("Columns dropped.")

    # Write to CSV
    df.to_csv(csv_path, index=False)
    print(f"Data written to {csv_path}")


def filter_and_split_dataframe(df, bucket_name, csv_path, drop_columns=False):
    # Identify columns matching the patterns
    columns_to_check = ["Question", "Response", "Interaction", "Interaction_Response"]
    threshold_map = {
        "Question": 4,
        "Response": 4,
        "Interaction": 3,
        "Interaction_Response": 3,
    }

    dropped_csv = bool(drop_columns)

    # Build regex pattern for matching the column names
    regex_patterns = [rf"{col}_\d+" for col in columns_to_check]

    # List to store columns to drop
    columns_to_drop = []

    for col in df.columns:
        for pattern, prefix in zip(regex_patterns, columns_to_check):
            if re.match(pattern, col):
                # Extract the number part to check the threshold
                num = int(col.split("_")[-1])
                if num >= threshold_map[prefix]:
                    columns_to_drop.append(col)

    print("Columns identified for potential drop:")
    print(columns_to_drop)

    # Create a second DataFrame with the dropped columns + 'Test_ID' and 'Job_Title'
    additional_columns = ["Test_ID", "Job_Title"]
    existing_additional_columns = [
        col for col in additional_columns if col in df.columns
    ]
    second_df_columns = columns_to_drop + existing_additional_columns
    second_df = df[second_df_columns]

    # Check if the columns to drop actually exist in the DataFrame before dropping them
    if drop_columns:
        columns_to_drop_existing = [col for col in columns_to_drop if col in df.columns]
        if columns_to_drop_existing:
            df = df.drop(columns=columns_to_drop_existing)
            print("Columns dropped from the main DataFrame.")
        else:
            print("No columns to drop in the main DataFrame.")

    # Check if any of the columns to filter on exist in second_df
    columns_to_check_rows = [
        "Question_4",
        "Response_4",
        "Interaction_3",
        "Interaction_Response_3",
    ]

    # Filter rows in the second DataFrame where all of the checked columns are empty
    existing_columns_to_check_rows = [
        col for col in columns_to_check_rows if col in second_df.columns
    ]

    if existing_columns_to_check_rows:
        second_df = second_df[
            second_df[existing_columns_to_check_rows].notna().any(axis=1)
        ]
        print(
            "Rows with empty 'Question_4', 'Response_4', 'Interaction_3', or 'Interaction_Response_3' removed."
        )
    else:
        print(
            "None of the specified columns for filtering are present in the second DataFrame."
        )
        dropped_csv = False

    print("Main DF:", df.columns)

    csv_text = df.to_csv(index=False)
    store_csv(csv_text, bucket_name, csv_path)
    # Write the first DataFrame to the original CSV path
    print(f"Main DataFrame written to {csv_path}")

    # Modify the filename to include '_dropped_cols'
    base, ext = os.path.splitext(csv_path)
    second_df_path = f"{base}_dropped_cols{ext}"

    if dropped_csv:
        # Write the second DataFrame to a CSV with '_dropped_cols' in the filename
        csv_text = second_df.to_csv(index=False)
        store_csv(csv_text, bucket_name, second_df_path)

        print(f"Second DataFrame written to {second_df_path}")


# TODO - refactor, too big
def generate_test_results_df(results, detailed=False):  # noqa: C901, PLR0912, PLR0915
    rows = []
    pass_count = 0
    fail_count = 0
    na_count = 0

    # List of basic columns to include in simple CSV format
    # basic_csv = [
    #     "Test_ID", "Job_Title", "Expected_SIC", "Final_Most_Likely_SIC",
    #     "Initial_Most_Likely_SIC", "Result", "Test_Notes",
    #     "Final_SIC_Confidence", "Initial_SIC_Confidence", "Total_Time_Secs",
    #     "Interaction_Time_Secs"
    # ]

    basic_csv = [
        "Test_ID",
        "Job_Title",
        "Final_Most_Likely_SIC",
        "Initial_Most_Likely_SIC",
        "Final_SIC_Confidence",
        "Initial_SIC_Confidence",
        "SIC_Lookup_String",
        "SIC_Lookup_Status",
        "SIC_Lookup_Code",
        "Test_Notes",
    ]

    # Collect all potential column names
    max_final_candidates = 0
    max_initial_candidates = 0
    max_questions = 0
    max_interactions = 0

    for result in results:
        # When initial and final is None, this indicates sic_lookup
        # was successful and survey assist was not used for initial
        # and final classification
        if result.classification["final"] is not None:
            max_final_candidates = max(
                max_final_candidates, len(result.classification["final"].candidates)
            )

        if result.classification["initial"] is not None:
            max_initial_candidates = max(
                max_initial_candidates, len(result.classification["initial"].candidates)
            )

        max_questions = max(max_questions, len(result.questions))
        max_interactions = max(max_interactions, len(result.interactions))

    # Base column order
    column_order = [
        "Test_ID",
        "Job_Title",
        "Final_Most_Likely_SIC",
        "Initial_Most_Likely_SIC",
        "Final_SIC_Confidence",
        "Initial_SIC_Confidence",
        "Total_Time_Secs",
        "Interaction_Time_Secs",
        "Final_Justification",
        "Initial_Justification",
        "SIC_Lookup_String",
        "SIC_Lookup_Status",
        "SIC_Lookup_Code",
        "Expected_SIC",
        "Result",
        "Test_Notes",
    ]

    # Add columns for final and initial candidates
    for x in range(1, max_final_candidates + 1):
        column_order.append(f"Final_Alternative_SIC_{x}")
        column_order.append(f"Final_Alternative_SIC_Confidence_{x}")

    for x in range(1, max_initial_candidates + 1):
        column_order.append(f"Initial_Alternative_SIC_{x}")
        column_order.append(f"Initial_Alternative_SIC_Confidence_{x}")

    # Add columns for questions and responses
    for x in range(1, max_questions + 1):
        column_order.append(f"Question_{x}")
        column_order.append(f"Response_{x}")

    # Add columns for interactions
    for x in range(1, max_interactions + 1):
        column_order.append(f"Interaction_{x}")
        column_order.append(f"Interaction_Response_{x}")

    for result in results:
        test_id = result.id
        job_title = result.questions[0].response if result.questions else "N/A"
        expected_sic = result.notes[0].expected_code if result.notes else "N/A"
        if expected_sic == "":
            expected_sic = "N/A"

        if (
            result.classification["final"] is not None
            and result.classification["initial"] is not None
        ):
            final_sic = result.classification["final"].ml_code
            initial_sic = result.classification["initial"].ml_code
            final_justification = result.classification["final"].justification
            initial_justification = result.classification["initial"].justification
            final_confidence = result.classification["final"].ml_confidence
            initial_confidence = result.classification["initial"].ml_confidence
            test_notes = result.notes[0].text if result.notes else "N/A"
            times = result.times
            result_status = (
                "N/A"
                if expected_sic == "N/A"
                else ("Pass" if expected_sic == final_sic else "Fail")
            )
        else:
            # If initial and final are None, this indicates sic_lookup
            # TODO - this is not ideal, need to handle this better
            final_sic = "N/A"
            initial_sic = "N/A"
            final_justification = "N/A"
            initial_justification = "N/A"
            test_notes = result.notes[0].text if result.notes else "N/A"
            final_confidence = 0.0
            initial_confidence = 0.0
            times = result.times
            result_status = (
                "N/A"
                if expected_sic == "N/A"
                else ("Pass" if expected_sic == final_sic else "Fail")
            )

        if result.sic_lookup:
            sic_lookup_status = result.sic_lookup["sic_found"]
            sic_lookup_string = result.sic_lookup["sic_lookup_string"]
            sic_lookup_code = result.sic_lookup["sic_lookup_response"].get(
                "sic_code", "N/A"
            )

        if result_status == "Pass":
            pass_count += 1
        elif result_status == "Fail":
            fail_count += 1
        else:
            na_count += 1

        # Prepare a row for the current result
        row = {
            "Test_ID": test_id,
            "Job_Title": job_title,
            "Expected_SIC": expected_sic,
            "Final_Most_Likely_SIC": final_sic,
            "Initial_Most_Likely_SIC": initial_sic,
            "Result": result_status,
            "Test_Notes": test_notes,
            "Final_SIC_Confidence": final_confidence,
            "Initial_SIC_Confidence": initial_confidence,
            "SIC_Lookup_String": sic_lookup_string,
            "SIC_Lookup_Status": sic_lookup_status,
            "SIC_Lookup_Code": sic_lookup_code,
            "Total_Time_Secs": times.total_time_secs,
            "Interaction_Time_Secs": times.interaction_time_secs,
            "Final_Justification": final_justification,
            "Initial_Justification": initial_justification,
        }

        if result.classification["final"] is not None:
            # Add final SIC candidates
            for x, candidate in enumerate(result.classification["final"].candidates, 1):
                row[f"Final_Alternative_SIC_{x}"] = candidate.code
                row[f"Final_Alternative_SIC_Confidence_{x}"] = candidate.confidence
        else:
            row["Final_Alternative_SIC_1"] = "N/A"
            row["Final_Alternative_SIC_Confidence_1"] = 0.0

        # Add initial SIC candidates
        if result.classification["initial"] is not None:
            for x, candidate in enumerate(
                result.classification["initial"].candidates, 1
            ):
                row[f"Initial_Alternative_SIC_{x}"] = candidate.code
                row[f"Initial_Alternative_SIC_Confidence_{x}"] = candidate.confidence
        else:
            row["Initial_Alternative_SIC_1"] = "N/A"
            row["Initial_Alternative_SIC_Confidence_1"] = 0.0

        # Add the question and response data
        for x, question in enumerate(result.questions, 1):
            row[f"Question_{x}"] = question.text
            row[f"Response_{x}"] = question.response

        # Add the interaction data
        for x, interaction in enumerate(result.interactions, 1):
            row[f"Interaction_{x}"] = interaction.text
            row[f"Interaction_Response_{x}"] = interaction.response

        rows.append(row)

    # Create the DataFrame from the rows list
    df = pd.DataFrame(rows)

    # Filter columns for basic CSV if detailed is False
    if not detailed:
        included_columns = []
        for col in basic_csv:
            if col.endswith("_"):
                # Include all columns matching the prefix
                included_columns.extend([c for c in df.columns if c.startswith(col)])
            else:
                # Include the specific column
                included_columns.append(col)
        df = df[[col for col in included_columns if col in df.columns]]
        # Filter column_order to only include items that are in basic_csv
        column_order = [col for col in column_order if col in basic_csv]

    # Reorder columns in the DataFrame
    # Ensure columns not in `column_order` are added to the end
    ordered_columns = column_order + [
        col for col in df.columns if col not in column_order
    ]

    df = df[ordered_columns]

    return df


def count_test_ids_by_user(username, df):
    """Count the number of rows in the DataFrame where the 'test_id' column starts with the given username.

    Args:
        username (str): The username to search for (e.g., 'jennifer.arkell').
        df (pd.DataFrame): The DataFrame containing the 'test_id' column.

    Returns:
        int: The count of rows where 'test_id' starts with the transformed username.
    """
    # Replace '.' in username with '' to match the format in test_id
    formatted_username = username.replace(".", "")

    # Filter rows where 'test_id' starts with the formatted username
    count = df["Test_ID"].str.startswith(formatted_username).sum()

    return count


def count_sic_changes(df):
    """Counts the number of rows where Final_Most_Likely_SIC and Initial_Most_Likely_SIC:
    - Remained the same
    - Differed.

    Args:
        df (pd.DataFrame): A DataFrame containing the columns 'Final_Most_Likely_SIC' and 'Initial_Most_Likely_SIC'.

    Returns:
        dict: A dictionary with counts for 'same' and 'different' rows.
    """
    # Check if the columns exist in the DataFrame
    if (
        "Final_Most_Likely_SIC" not in df.columns
        or "Initial_Most_Likely_SIC" not in df.columns
    ):
        raise ValueError(
            "DataFrame must contain 'Final_Most_Likely_SIC' and 'Initial_Most_Likely_SIC' columns."
        )

    # Calculate the counts
    same_count = (df["Final_Most_Likely_SIC"] == df["Initial_Most_Likely_SIC"]).sum()
    different_count = (
        df["Final_Most_Likely_SIC"] != df["Initial_Most_Likely_SIC"]
    ).sum()

    return {"same": same_count, "different": different_count}


def calculate_average_interaction_time(df):
    """Calculates the average interaction time in seconds from the Interaction_Time_Secs column.

    Args:
        df (pd.DataFrame): A DataFrame containing the column 'Interaction_Time_Secs'.

    Returns:
        float: The average interaction time in seconds.
    """
    # Check if the column exists in the DataFrame
    if "Interaction_Time_Secs" not in df.columns:
        raise ValueError("DataFrame must contain 'Interaction_Time_Secs' column.")

    # Calculate the mean of the Interaction_Time_Secs column
    return df["Interaction_Time_Secs"].mean()


def calculate_average_excluding_max(df):
    """Calculates the average interaction time in seconds, excluding the maximum value,
    unless there are not enough rows to remove the maximum.

    Args:
        df (pd.DataFrame): A DataFrame containing the column 'Interaction_Time_Secs'.

    Returns:
        float: The average interaction time in seconds, excluding the maximum value.
               If not enough data to exclude the maximum, returns the average of all values.
    """
    # Check if the column exists in the DataFrame
    if "Interaction_Time_Secs" not in df.columns:
        raise ValueError("DataFrame must contain 'Interaction_Time_Secs' column.")

    # Exclude NaN values
    filtered_times = df["Interaction_Time_Secs"].dropna()

    # If there are only two values, we can't exclude the max, so return the mean of the available values
    if len(filtered_times) <= 2:  # noqa: PLR2004
        return filtered_times.mean()

    # Exclude the maximum value only if there are more than one row
    max_value = filtered_times.max()
    filtered_times = filtered_times[filtered_times != max_value]

    # Calculate the mean of the remaining values
    return filtered_times.mean()


def count_non_empty_test_notes(df):
    """Counts the number of rows where the 'Test_Notes' column is not empty or 'N/A'.

    Args:
        df (pd.DataFrame): A DataFrame containing the 'Test_Notes' column.

    Returns:
        int: The count of rows where 'Test_Notes' is not empty or 'N/A'.
    """
    # Check if the column exists in the DataFrame
    if "Test_Notes" not in df.columns:
        raise ValueError("DataFrame must contain 'Test_Notes' column.")

    # Count rows where 'Test_Notes' is not an empty string or 'N/A'
    valid_rows = df["Test_Notes"].apply(lambda x: x not in ["", "N/A"])

    # Return the count of valid rows
    return valid_rows.sum()


def generate_user_cards(user_totals):
    html_output = ""

    for user in user_totals:
        if user.get("user") and user.get("total") is not None:
            user_name = user["user"]
            total_tests = user["total"]

            # Generate the HTML string for each user
            user_card_html = f"""
            <div class="ons-grid__col ons-col-3@m">
                <div class="card">
                    <div class="number">{total_tests}</div>
                    <div class="label">{user_name}</div>
                </div>
                <br></br>
            </div>
            """

            # Append the generated card to the output
            html_output += user_card_html

    return html_output


def store_csv(csv_content, bucket_name, gcs_path, content_type="text/csv"):
    """Uploads a string as a file to a GCP bucket.

    Args:
        csv_content (str): The content to upload (e.g., CSV data).
        bucket_name (str): The name of the GCP bucket.
        gcs_path (str): The full path in the bucket where the file should be saved.
        content_type (str): The MIME type of the file (default: 'text/csv').

    Returns:
        str: The full GCS file path (e.g., gs://bucket_name/gcs_path) if successful.
        None: If an error occurs during upload.
    """
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)

        # Upload the content
        blob.upload_from_string(csv_content, content_type=content_type)

        # Construct the GCS file path
        gcs_file_path = f"gs://{bucket_name}/{gcs_path}"
        print(f"File successfully uploaded to {gcs_file_path}")
        return gcs_file_path
    except Exception as e:
        print(f"Failed to upload file to GCS: {e}")
        return None


def generate_results_filename(user, base_folder):

    # Remove the @email.address element from the user
    user = user.split("@")[0]

    # Generate file name
    user_sanitized = user.replace(".", "").lower()
    now = datetime.now()
    date_str = now.strftime("%d%m%Y")
    time_str = now.strftime("%H%M%S")
    file_name = f"results_detailed_{user_sanitized}_{date_str}_{time_str}.csv"

    # Full path in GCS
    results_name = f"{base_folder}/Results/{file_name}"
    print(f"Generated Path: {results_name}")

    return results_name


def format_users_for_checkboxes(users):
    """Formats a list of users into a structure suitable for a Nunjucks template.

    Args:
        users (list): A list of user strings.

    Returns:
        list: A list of dictionaries formatted for Nunjucks.
    """
    formatted_users = []
    for user in users:
        user_id = user.split("@")[0].replace(".", "-").replace(" ", "-").lower()
        user_value = user.split("@")[0].lower()
        formatted_users.append(
            {
                "id": f"user-checkbox-{user_id}",
                "name": "users",
                "label": {"text": user_value},
                "value": user_value,
            }
        )
    return formatted_users


def stream_file_from_store(bucket_name, source_blob_name):
    """Streams a file from GCP Storage to the user's device.

    Args:
        bucket_name (str): Name of the GCP bucket.
        source_blob_name (str): Path to the file in the bucket.
        (e.g., "TLFS_PoC/Results/results_detailed_stevegibbard_19122024_123341.csv").

    Returns:
        Flask Response: Streamed file served to the user's device for download.
    """
    try:
        # Initialize GCS client
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)

        # Get the filename from the blob path
        filename = source_blob_name.split("/")[-1]

        print(f"Streaming file: {filename}")

        # Stream the blob content
        def generate():
            with blob.open("rb") as blob_stream:
                yield from blob_stream

        # Return the streamed content as a response
        return Response(
            generate(),
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        print(f"An error occurred while streaming the file: {e}")
        raise
