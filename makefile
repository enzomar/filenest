.PHONY: help install run docker docker-build docker-stop clean reset

# Default target
help:  ## Show this help message
	@echo ""
	@echo "📁 FileNest Makefile - Usage Guide"
	@echo "==================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "make \033[36m%-14s\033[0m # %s\n", $$1, $$2}'
	@echo ""

PYTHON := python3
VENV_DIR := .venv
ACTIVATE := source $(VENV_DIR)/bin/activate

install:  ## Create venv and install dependencies
	@if [ ! -d "$(VENV_DIR)" ]; then \
		$(PYTHON) -m venv $(VENV_DIR); \
		echo "Virtualenv created."; \
	else \
		echo "Virtualenv already exists."; \
	fi
	@$(ACTIVATE) && pip install --upgrade pip && pip install -r backend/requirements.txt

run:  ## Run FastAPI locally using uvicorn (venv required)
	@$(ACTIVATE) && cd backend && ENV=dev uvicorn main:app --reload --host 0.0.0.0 --port 8000

unittest:  ## Run unit tests using pytest (venv required)
	@$(ACTIVATE) && pytest

docker:  ## Run the app using docker-compose
	@docker-compose up

docker-build:  ## Build and run the app with docker-compose
	@docker-compose up --build

docker-stop:  ## Stop and remove Docker containers
	@docker-compose down

clean:  ## Delete the virtual environment
	@rm -rf $(VENV_DIR)

reset: clean install  ## Clean and reinstall venv
