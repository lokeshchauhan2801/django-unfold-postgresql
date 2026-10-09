.PHONY: help install frontend-install frontend-build migrate run test lint shell createsuperuser \
        celery-worker celery-beat \
        makemigrations collectstatic

PYTHON := venv/bin/python
PIP    := venv/bin/pip
MANAGE := $(PYTHON) manage.py

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies (local)
	$(PIP) install -r requirements/local.txt

frontend-install:  ## Install React frontend dependencies
	cd frontend && npm ci

frontend-build:  ## Build the React frontend into Django static files
	cd frontend && npm run build

migrate:  ## Apply database migrations
	$(MANAGE) migrate

makemigrations:  ## Create new migrations
	$(MANAGE) makemigrations

run: frontend-build  ## Build frontend and start development server
	$(MANAGE) runserver

shell:  ## Open Django shell
	$(MANAGE) shell

createsuperuser:  ## Create admin superuser
	$(MANAGE) createsuperuser

collectstatic:  ## Collect static files
	$(MANAGE) collectstatic --noinput

test:  ## Run tests
	$(MANAGE) test

lint:  ## Run ruff linter
	venv/bin/ruff check ai audit auth base basics chat company config docs infrastructure scrapper tests

format:  ## Format code
	venv/bin/ruff format ai audit auth base basics chat company config docs infrastructure scrapper tests

celery-worker:  ## Start Celery worker (local)
	venv/bin/celery -A base.celery worker --loglevel=info --concurrency=4

celery-beat:  ## Start Celery beat scheduler (local)
	venv/bin/celery -A base.celery beat --loglevel=info

env:  ## Copy .env.example to .env
	cp .env.example .env
	@echo '.env created — fill in your secrets'
