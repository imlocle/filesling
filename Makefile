.PHONY: help install dev-install build test lint format clean run release

PYTHON = .venv/bin/python
PIP = .venv/bin/pip

help:
	@echo "FileSling — Build & Development"
	@echo "=============================="
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make dev-install   Install with development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run           Run the application"
	@echo "  make format        Format code (black, isort)"
	@echo "  make lint          Run linting checks (flake8)"
	@echo "  make test          Run tests with coverage (437 tests)"
	@echo ""
	@echo "Build & Release:"
	@echo "  make build         Build wheel and source distributions"
	@echo "  make release V=X.Y.Z   Bump version, merge to main, tag, push"
	@echo "  make clean         Remove build artifacts and cache"

install:
	$(PIP) install -r requirements.txt

dev-install:
	$(PIP) install -r requirements-dev.txt

run:
	$(PYTHON) main.py

format:
	$(PYTHON) -m black src main.py
	$(PYTHON) -m isort src main.py

lint:
	$(PYTHON) -m flake8 src main.py

test:
	$(PYTHON) -m pytest

build: clean
	$(PYTHON) -m build

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.py[cod]' -delete
	rm -rf .pytest_cache/ .coverage htmlcov/

# ==============================================================================
# Release — bumps version, merges to main, tags, and pushes
# Usage: make release V=2.4.0
# ==============================================================================
release:
ifndef V
	$(error Usage: make release V=X.Y.Z)
endif
	@echo "🚀 Releasing FileSling v$(V)..."
	@echo ""
	@# 1. Update version in pyproject.toml
	@sed -i '' 's/^version = ".*"/version = "$(V)"/' pyproject.toml
	@# 2. Update version in constants.py
	@sed -i '' 's/^VERSION = ".*"/VERSION = "$(V)"/' src/utils/constants.py
	@# 3. Commit
	git add pyproject.toml src/utils/constants.py
	git commit -m "bump version to $(V)"
	git push origin dev
	@# 5. Merge to main
	git checkout main
	git merge dev
	git push origin main
	@# 6. Tag and push
	git tag v$(V)
	git push origin v$(V)
	@# 7. Back to dev
	git checkout dev
	@echo ""
	@echo "✅ Released v$(V) — GitHub Actions will build the .dmg"
