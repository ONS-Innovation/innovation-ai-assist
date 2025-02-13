import json
from datetime import datetime

from flask import session


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
