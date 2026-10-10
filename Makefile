SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
FRONTEND := frontend
MOCK_ERP := mock-erp
UV ?= uv
COMPOSE ?= docker compose

.PHONY: help setup dev dev-backend dev-frontend dev-mock test test-backend test-frontend \
        lint format typecheck e2e e2e-local demo generate-invoices openapi up down logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies (backend, mock-erp, frontend, playwright)
	cd $(BACKEND) && $(UV) sync
	cd $(MOCK_ERP) && $(UV) sync
	cd $(FRONTEND) && npm ci
	@[ -f .env ] || cp .env.example .env
	-pre-commit install

dev: ## Run backend + frontend locally with hot reload (SQLite, mock LLM)
	@trap 'kill 0' EXIT; $(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend: ## Run the API on :8000
	cd $(BACKEND) && $(UV) run alembic upgrade head && $(UV) run uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run the Vite dev server on :5173
	cd $(FRONTEND) && npm run dev

dev-mock: ## Run the frontend against MSW mocks only (no backend)
	cd $(FRONTEND) && npm run dev:mock

test: test-backend test-frontend ## Run unit + integration tests

test-backend: ## Backend tests with coverage (>=85%)
	cd $(BACKEND) && $(UV) run pytest --cov --cov-report=term-missing
	cd $(MOCK_ERP) && $(UV) run pytest

test-frontend: ## Frontend tests with coverage (>=80%)
	cd $(FRONTEND) && npm run test:coverage

lint: ## Lint + format check + type check everything
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy .
	cd $(MOCK_ERP) && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy .
	cd $(FRONTEND) && npm run lint && npm run format:check && npm run typecheck

format: ## Auto-format all code
	cd $(BACKEND) && $(UV) run ruff check --fix . && $(UV) run ruff format .
	cd $(MOCK_ERP) && $(UV) run ruff check --fix . && $(UV) run ruff format .
	cd $(FRONTEND) && npm run format

openapi: ## Regenerate OpenAPI schema + TypeScript API types
	cd $(BACKEND) && $(UV) run python -m scripts.export_openapi ../$(FRONTEND)/openapi.json
	cd $(FRONTEND) && npm run gen:api

up: ## Start the full stack with docker compose
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack
	$(COMPOSE) down -v

logs: ## Tail stack logs
	$(COMPOSE) logs -f

e2e: up ## Run Playwright E2E tests against docker compose
	cd $(FRONTEND) && npx playwright install --with-deps chromium && npm run e2e

demo: up ## Start the stack and seed it with the sample invoices
	$(COMPOSE) exec -T backend python -m scripts.seed_demo --api http://localhost:8000
	@echo "Open http://localhost:8080"

generate-invoices: ## Regenerate mock invoice fixtures + sample data
	cd $(BACKEND) && $(UV) run python -m scripts.generate_invoices --count 10 --out tests/fixtures/invoices --copy-to ../sample-data

clean: ## Remove caches and build output
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache $(BACKEND)/htmlcov $(BACKEND)/.coverage
	rm -rf $(FRONTEND)/dist $(FRONTEND)/coverage $(FRONTEND)/playwright-report $(FRONTEND)/test-results
