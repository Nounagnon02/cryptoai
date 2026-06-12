.PHONY: help install install-dev lint format typecheck test test-cov clean dev docker-up docker-down docker-build db-upgrade db-migrate run run-worker run-scheduler

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Installation ────────────────────────────────────────────────

install: ## Install production dependencies
	pip install -e .

install-dev: install ## Install dev dependencies
	pip install -e ".[dev]"
	pre-commit install

# ─── Qualité du code ────────────────────────────────────────────

lint: ## Run linter (ruff)
	ruff check src/ tests/

format: ## Format code (ruff)
	ruff format src/ tests/

typecheck: ## Run type checker (mypy)
	mypy src/

# ─── Tests ──────────────────────────────────────────────────────

test: ## Run tests
	pytest tests/ -v

test-cov: ## Run tests with coverage
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	pytest tests/unit -v

test-integration: ## Run integration tests only
	pytest tests/integration -v

test-parallel: ## Run tests in parallel
	pytest tests/ -n auto -v

# ─── Développement ──────────────────────────────────────────────

dev: ## Start dev environment (API + workers)
	@echo "Starting CryptoAI development environment..."
	docker compose up -d postgres redis
	uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

run: ## Run full system in paper mode
	python -m src.main --mode paper --config configs/default.yaml

run-live: ## Run full system in live mode
	python -m src.main --mode live --config configs/default.yaml

run-worker: ## Run background worker (data collection, analysis)
	python -m src.main --worker

# ─── Docker ─────────────────────────────────────────────────────

docker-up: ## Start all services
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-build: ## Build images
	docker compose build

docker-logs: ## View logs
	docker compose logs -f

docker-reset: ## Reset all data
	docker compose down -v

# ─── Base de données ────────────────────────────────────────────

db-upgrade: ## Run database migrations
	alembic upgrade head

db-migrate: ## Create new migration
	@read -p "Migration name: " name; alembic revision --autogenerate -m "$$name"

db-rollback: ## Rollback last migration
	alembic downgrade -1

# ─── Backtesting ───────────────────────────────────────────────

backtest: ## Run backtest for a strategy
	python -m src.backtesting.cli --config configs/default.yaml

# ─── Nettoyage ──────────────────────────────────────────────────

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage
	rm -rf .nox/

clean-all: clean ## Full cleanup (including data)
	rm -rf data/raw/* data/processed/*
	rm -rf logs/*.log
	@echo "✅ Clean complete"
