.PHONY: help install dev test lint format clean build release

help:
	@echo "Available commands:"
	@echo "  make install    Install the package"
	@echo "  make dev        Install for development"
	@echo "  make test       Run tests"
	@echo "  make test-cov   Run tests with coverage"
	@echo "  make lint       Run linting"
	@echo "  make format     Format code"
	@echo "  make clean      Clean up cache files"
	@echo "  make build      Build distribution packages"
	@echo "  make release    Upload to PyPI (requires auth)"

install:
	uv pip install .

dev:
	uv sync

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=mastodon_to_bluesky --cov-report=term-missing

lint:
	uv run ruff check src/ tests/ --fix --extend-select I --unsafe-fixes

format:
	uv run ruff format src/ tests/

clean:
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf src/*.egg-info/
	rm -rf dist/
	rm -rf build/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	uv build

release: build
	uv publish