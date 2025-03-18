"""Provides logging for the project.

Used to set up file and console based loggers.
Typically called from an entry point or external script.

Typical usage:

    ```
    logger = logs.setup_logging("some_script_name")
    ```
    This will create a separate log file for the `some_script_name`.
"""

import datetime
import functools
import inspect
import logging
import sys
from pathlib import Path
from typing import Optional, Union

LOG_FORMAT = "%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MODULE_NAME = "survey_assist"
EXTRA_MODULE_NAME = "flask"
LOG_LEVEL = logging.DEBUG
DATE_STRING = f"{datetime.datetime.now().date()}"

# Logging can be used independently of configuration
LOG_DIR = Path.home() / "logs"


def setup_logging(
    script_name: Optional[str] = None, log_dir: Union[Path, str] = LOG_DIR
) -> logging.Logger:
    """Set up console and file logging.
    This will create a directory to log to if it doesn't already exist.
    Safe to call in interactive environments without duplicating the logging.
    Logs on the same day will append to the same file for the same script_name.

    Args:
        script_name (str): Used in the filename for the logs.
        log_dir (Path or str): Directory to store logs in. Defaults to "~/logs".

    Returns:
        Logger object with handlers set up.
    """
    logger = logging.getLogger(MODULE_NAME)
    logger.setLevel(logging.DEBUG)

    other_logger = logging.getLogger(EXTRA_MODULE_NAME)
    other_logger.setLevel(logging.DEBUG)

    # Used when writing to local logging file
    # log_dir = Path(log_dir)
    # log_dir.mkdir(parents=True, exist_ok=True)

    # Remove sys.stdout if logging locally
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    ch.setFormatter(formatter)

    # In case this is called twice check whether a handler is already registered
    if not logger.handlers:
        logger.addHandler(ch)
        other_logger.addHandler(ch)

    # Used when writing to local logging file
    # try:
    #     if script_name is None:
    #         log_file = log_dir / f"{MODULE_NAME}.{DATE_STRING}.log"
    #     else:
    #         log_file = log_dir / f"{MODULE_NAME}_{script_name}.{DATE_STRING}.log"

    #     if len(logger.handlers) == 1:
    #         fh = logging.FileHandler(log_file)

    #         fh.setFormatter(formatter)
    #         fh.setLevel(LOG_LEVEL)
    #         logger.addHandler(fh)
    #         other_logger.addHandler(fh)

    # except FileNotFoundError:
    #     logger.warning("Console logging only")

    return logger


def log_entry(logger):
    """Decorator to log function entry with method name and line number."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            frame = inspect.currentframe().f_back
            line_no = frame.f_lineno  # Get line number where the function was called
            logger.debug(f"Entering {func.__name__}() at line {line_no}")
            return func(*args, **kwargs)

        return wrapper

    return decorator
