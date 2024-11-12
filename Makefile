.PHONY: all
all: ## Show the available make targets.
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@fgrep "##" Makefile | fgrep -v fgrep

.PHONY: clean
clean: ## Clean the temporary files.
	rm -rf .mypy_cache
	rm -rf .ruff_cache	

DESIGN_SYSTEM_VERSION=`cat .design-system-version`

load-design-system-templates:  ## Load the design system templates
	./get_design_system.sh

run-ui: ## Run the UI
	poetry run flask --app ai_assist_builder run --debug -p 8000

format-python: ## Format the python code (auto fix)
	poetry run isort . --verbose
	poetry run flake8 .
	poetry run black .
	poetry run ruff check . --fix

format-python-nofix: ## Format the python code (no fix)
	poetry run isort . --check --verbose
	poetry run flake8 . 
	poetry run black . --check
	poetry run ruff check .

black: ## Run black
	poetry run black .

install: ## Install the dependencies
	poetry install --only main --no-root

install-dev: ## Install the dev dependencies
	poetry install --no-root
