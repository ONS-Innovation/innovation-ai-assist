# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    JWT_SECRET=/app/jwt-secret.json


# Install system dependencies and Poetry
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        gcc \
        libffi-dev \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY ai_assist_builder ./ai_assist_builder
COPY main.py ./
COPY ai-assist-tlfs-poc-secret.json /app/jwt-secret.json

# Install dependencies
RUN poetry install --no-root --only main

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Change ownership to non-root user
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Run the application using Flask's built-in server for development purposes
CMD ["poetry", "run", "flask", "--app", "main:app", "run", "--host", "0.0.0.0", "--port", "8000"] 