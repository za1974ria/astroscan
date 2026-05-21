.PHONY: help test test-smoke test-unit test-integration test-cov \
        lint format format-check precommit \
        start stop restart logs docker-build docker-up docker-down \
        install-dev clean-cov

# Default target: print help so `make` alone is friendly.
.DEFAULT_GOAL := help

# Use the project venv if present, otherwise fall back to python3 in PATH.
PY ?= $(shell test -x venv/bin/python && echo venv/bin/python || echo python3)
PYTEST ?= $(PY) -m pytest

help:
	@echo "ASTRO-SCAN — make targets"
	@echo ""
	@echo "  Testing"
	@echo "    test               — run all tests (smoke + unit + integration)"
	@echo "    test-smoke         — smoke tests only (no external deps)"
	@echo "    test-unit          — unit tests only (pure logic)"
	@echo "    test-integration   — integration tests (DB / network)"
	@echo "    test-cov           — full suite with coverage (term + HTML)"
	@echo ""
	@echo "  Code quality"
	@echo "    lint               — ruff check (Axe 1 scope: tests/)"
	@echo "    format             — ruff format (apply, Axe 1 scope)"
	@echo "    format-check       — ruff format --check (no-op verification)"
	@echo "    precommit          — run all pre-commit hooks on all files"
	@echo ""
	@echo "  Setup"
	@echo "    install-dev        — install dev deps + pre-commit hooks"
	@echo "    clean-cov          — remove coverage artifacts"
	@echo ""
	@echo "  Service / Docker"
	@echo "    start | stop | restart | logs"
	@echo "    docker-build | docker-up | docker-down"

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ --tb=short

test-smoke:
	$(PYTEST) tests/smoke/ -m "not integration" --tb=short

test-unit:
	$(PYTEST) tests/unit/ --tb=short

test-integration:
	$(PYTEST) tests/integration/ --tb=short

test-cov:
	$(PYTEST) tests/ \
		--cov=app --cov=services \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml \
		--tb=short

# ── Code quality (Axe 1 — ruff is the single source of truth) ────────────────

lint:
	$(PY) -m ruff check tests/

format:
	$(PY) -m ruff format tests/
	$(PY) -m ruff check tests/ --fix

format-check:
	$(PY) -m ruff format --check tests/
	$(PY) -m ruff check tests/

precommit:
	$(PY) -m pre_commit run --all-files

# ── Setup ────────────────────────────────────────────────────────────────────

install-dev:
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m pip install pre-commit ruff
	$(PY) -m pre_commit install

clean-cov:
	rm -rf htmlcov/ .coverage coverage.xml

# ── Service control ──────────────────────────────────────────────────────────

start:
	systemctl start astroscan

stop:
	systemctl stop astroscan

restart:
	systemctl restart astroscan && sleep 2 && systemctl is-active astroscan

logs:
	journalctl -u astroscan -f --no-pager

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build:
	docker build -t astroscan .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down
