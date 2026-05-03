.PHONY: test test-smoke test-unit test-integration test-cov \
        start stop restart logs docker-build docker-up docker-down \
        install-dev

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	python3 -m pytest tests/ --tb=short

test-smoke:
	python3 -m pytest tests/smoke/ -m "not integration" --tb=short

test-unit:
	python3 -m pytest tests/unit/ --tb=short

test-integration:
	python3 -m pytest tests/integration/ --tb=short

test-cov:
	python3 -m pytest tests/ \
		--cov=app --cov=services \
		--cov-report=term-missing --cov-report=html \
		--tb=short

install-dev:
	pip install -r requirements-dev.txt

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
