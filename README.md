# AI Assist (Proof of Concept for TLFS)

## Objective

Demonstrate to stakeholders how AI can enhance survey questions to improve response rates.

## Setup Instructions

1. Clone repository:

    ```bash
    git clone https://github.com/ONS-Innovation/innovation-ai-assist
    ```

2. Install `wget`:

    ```bash
    brew install wget
    ```

3. Install dependencies:

    ```bash
    make install
    ```

4. Load design system templates:

    ```bash
    make load-design-system-templates
    ```

5. Run the UI:

    ```bash
    make run-ui
    ```

## Containerising

This repository utilises Docker and Colima to containerise the application.

Install Colima (if needed):

```bash
brew install colima
```

Start Colima (if using):

```bash
make colima-start
```

Build the Docker image:

```bash
make docker-build
```

Run the Docker container. The application will be available at http://0.0.0.0:8000:

*If you would like to edit the environment variables, you can do so by editing the this `Makefile` command.*

```bash
make docker-run
```

Stop the Docker container:

```bash
make docker-stop
```

Stop Colima (if using):

```bash
make colima-stop
```

To clean up Docker resources:

```bash
make docker-clean
```

To check the status of Colima:

```bash
make colima-status
```

## Linting and Formatting

Install dev dependencies:

```bash
make install-dev
```

This repository utilises isort, flake8, black and ruff:

These two commands will run the linting with and without fixing:

Format the code with fixing:

```bash
make format-python
```

Format the code without fixing:

```bash
make format-python-no-fix
```

Run black:

```bash
make black
```

Remember to clean temporary files when finished testing:

```bash
make clean
```

To view all make commands run:

```bash
make all
```

## Scripts

**scripts/generate_jwt.py** - used to generate a JWT token to test API interactions.
**scripts/sic_word_count.py** - used to create JSON outputs from the sic knowledge base file
