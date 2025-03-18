import json
import re
from datetime import datetime

from flask import session

MIN_USER_LENGTH = 6


def custom_serializer(obj):
    """Custom serializer for JSON."""
    if isinstance(obj, datetime):
        return obj.isoformat()  # Convert datetime to a string
    raise TypeError(f"Type {type(obj)} not serializable")


def print_session_size():
    # Get the session data as a JSON string
    session_data = json.dumps(dict(session), default=custom_serializer)
    session_size = len(session_data.encode("utf-8"))

    print(f"Session size: {session_size} bytes")
    return session_size


def print_session():
    # Pretty print the session data
    print(
        json.dumps(dict(session), indent=4, sort_keys=True, default=custom_serializer)
    )


def log_session(logger):
    # Pretty print the session data
    logger.debug(
        json.dumps(dict(session), indent=4, sort_keys=True, default=custom_serializer)
    )


def log_api_send(logger, api_endpoint, request_data):
    logger.debug(f"SND To: {api_endpoint}")

    if request_data is not None:
        logger.debug(
            json.dumps(
                dict(request_data), indent=4, sort_keys=True, default=custom_serializer
            )
        )
    else:
        logger.debug("No body data")


def log_api_rcv(logger, api_endpoint, response_data):
    logger.debug(f"RCV From: {api_endpoint}")
    # Pretty print the session data
    logger.debug(
        json.dumps(
            dict(response_data), indent=4, sort_keys=True, default=custom_serializer
        )
    )


def mask_username(email):
    username = email.split("@")[0]
    if len(username) < MIN_USER_LENGTH:
        masked_name = re.sub(r"(?<=.{1}).(?=.{1})", "*", username)
    else:
        masked_name = re.sub(r"(?<=.{3}).(?=.{3})", "*", username)
    return masked_name
