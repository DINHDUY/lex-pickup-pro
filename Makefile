SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_DIR := backend
FRONTEND_DIR := frontend
UV := uv
NPM := npm
COMPOSE := docker compose

.PHONY: help \
	install backend-install frontend-install backend-env backend-migrate backend-seed-demo \
	backend-dev frontend-dev dev \
	docker-up docker-down docker-build docker-logs \
	frontend-build backend-lint backend-test backend-check backend-format \
	frontend-lint frontend-format frontend-test-e2e frontend-preview \
	lint test check build package format clean \
	reminders

help:
	@printf "Usage:\n"
	@printf "  make install            Install backend + frontend dependencies\n"
	@printf "  make setup              Copy env files and initialize the local database\n"
	@printf "  make backend-dev        Run the FastAPI backend with reload\n"
	@printf "  make frontend-dev       Run the Vite frontend\n"
	@printf "  make dev               Run backend + frontend together\n"
	@printf "  make docker-up          Build and start the full Docker Compose stack\n"
	@printf "  make docker-down        Stop the Docker Compose stack\n"
	@printf "  make build              Build frontend and Docker artifacts\n"
	@printf "  make package            Alias for build\n"
	@printf "  make test               Run backend + frontend test suites\n"
	@printf "  make lint               Run backend + frontend lint checks\n"
	@printf "  make format             Format backend + frontend code\n"
	@printf "  make check              Run lint + tests + migration validation\n"
	@printf "  make clean              Remove generated build and dependency directories\n"
	@printf "  make reminders         Preview reminder delivery output\n"

install: backend-install frontend-install

backend-install:
	cd $(BACKEND_DIR) && $(UV) python install 3.12
	cd $(BACKEND_DIR) && $(UV) sync --frozen

frontend-install:
	cd $(FRONTEND_DIR) && $(NPM) ci

backend-env:
	cp -n $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env 2>/dev/null || true

setup: backend-env backend-migrate backend-seed-demo

backend-migrate: backend-env
	cd $(BACKEND_DIR) && $(UV) run alembic upgrade head

backend-seed-demo: backend-env
	cd $(BACKEND_DIR) && $(UV) run python -m app.seed --demo

backend-dev: backend-env
	cd $(BACKEND_DIR) && $(UV) run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend-dev:
	cd $(FRONTEND_DIR) && $(NPM) run dev

dev:
	@echo "Starting backend and frontend in parallel..."
	$(MAKE) -j2 backend-dev frontend-dev

backend-check: backend-lint backend-test
	cd $(BACKEND_DIR) && $(UV) run alembic check

backend-lint:
	cd $(BACKEND_DIR) && $(UV) run ruff check app tests

backend-test:
	cd $(BACKEND_DIR) && $(UV) run pytest -q

backend-format:
	cd $(BACKEND_DIR) && $(UV) run ruff format app tests alembic

frontend-lint:
	cd $(FRONTEND_DIR) && $(NPM) run lint

frontend-format:
	cd $(FRONTEND_DIR) && $(NPM) run format

frontend-build:
	cd $(FRONTEND_DIR) && $(NPM) run build

frontend-preview:
	cd $(FRONTEND_DIR) && $(NPM) run preview

frontend-test-e2e:
	cd $(FRONTEND_DIR) && npx playwright install chromium && $(NPM) run test:e2e

build: frontend-build docker-build

package: build

docker-build:
	$(COMPOSE) build

docker-up:
	$(COMPOSE) up --build

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f

lint: backend-lint frontend-lint

test: backend-test frontend-test-e2e

check: lint backend-check

format: backend-format frontend-format

reminders:
	cd $(BACKEND_DIR) && $(UV) run python -m app.reminders

clean:
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/playwright-report $(FRONTEND_DIR)/test-results
	rm -rf $(BACKEND_DIR)/.venv
