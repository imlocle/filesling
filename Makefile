.PHONY: help install dev-install build test lint format clean run release

PYTHON = python3
PIP = pip3

help:
	@echo "Shuttle — Build & Development"
	@echo "=============================="
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make dev-install   Install with development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run           Run the application"
	@echo "  make format        Format code (black, isort)"
	@echo "  make lint          Run linting checks (flake8, mypy)"
	@echo "  make test          Run tests with coverage"
	@echo ""
	@echo "Build & Release:"
	@echo "  make build         Build wheel and source distributions"
	@echo "  make clean         Remove build artifacts and cache"

install:
	$(PIP) install -r requirements.txt

dev-install:
	$(PIP) install -r requirements-dev.txt

run:
	$(PYTHON) main.py

format:
	autoflake --in-place --remove-all-unused-imports -r src main.py
	black src main.py
	isort src main.py

lint:
	flake8 src main.py

test:
	pytest

build: clean
	$(PYTHON) -m build

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.py[cod]' -delete
	rm -rf .pytest_cache/ .coverage htmlcov/
