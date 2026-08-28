## JARVIS — Makefile
## Usage: make <target>
## Windows: Install make via `winget install GnuWin32.Make` or use Git Bash

.PHONY: help install install-dev test test-fast test-cov lint format typecheck clean build build-exe docs

# ── Default ──────────────────────────────────────────────────────
help:
	@echo ""
	@echo " JARVIS v4.0.0 — Available Commands"
	@echo " ======================================"
	@echo ""
	@echo " Setup:"
	@echo "   make install        Install core dependencies"
	@echo "   make install-dev    Install + dev tools (pytest, ruff, mypy)"
	@echo "   make install-hooks  Setup pre-commit hooks"
	@echo ""
	@echo " Development:"
	@echo "   make run            Run JARVIS (tray mode)"
	@echo "   make run-console    Run JARVIS (console mode)"
	@echo ""
	@echo " Testing:"
	@echo "   make test           Run all 633 unit tests"
	@echo "   make test-fast      Run tests (no slow tests)"
	@echo "   make test-cov       Run tests with HTML coverage report"
	@echo "   make test-file f=<file>  Run specific test file"
	@echo ""
	@echo " Code Quality:"
	@echo "   make lint           Check code with Ruff"
	@echo "   make format         Auto-format code with Ruff"
	@echo "   make typecheck      Type check with mypy"
	@echo "   make check          lint + format + typecheck"
	@echo ""
	@echo " Build:"
	@echo "   make build          Build JARVIS.exe"
	@echo "   make build-check    Check build environment"
	@echo "   make build-installer  Build Windows installer"
	@echo ""
	@echo " Maintenance:"
	@echo "   make health         Run health check report"
	@echo "   make clean          Remove build artifacts"
	@echo "   make changelog      View latest changelog"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install ruff mypy pytest-cov pre-commit

install-hooks:
	pre-commit install
	pre-commit install --hook-type commit-msg
	@echo "Pre-commit hooks installed."

# ── Run ───────────────────────────────────────────────────────────
run:
	python main.py --tray

run-console:
	python main.py

# ── Testing ───────────────────────────────────────────────────────
test:
	python -m pytest tests/unit/ -v --timeout=60

test-fast:
	python -m pytest tests/unit/ -v --timeout=60 -m "not slow"

test-cov:
	python -m pytest tests/unit/ --cov=jarvis --cov-report=html --cov-report=term --timeout=60
	@echo "Coverage report: htmlcov/index.html"

test-file:
	python -m pytest $(f) -v --timeout=60

test-quick:
	python -m pytest tests/unit/ -q --tb=no --timeout=30

# ── Code Quality ──────────────────────────────────────────────────
lint:
	python -m ruff check jarvis/ tests/ --output-format=concise

format:
	python -m ruff format jarvis/ tests/
	python -m ruff check jarvis/ tests/ --fix

typecheck:
	python -m mypy jarvis/ --ignore-missing-imports

check: lint typecheck
	@echo "All checks passed!"

# ── Build ─────────────────────────────────────────────────────────
build:
	python scripts/build_installer.py --exe-only

build-check:
	python scripts/build_installer.py --check

build-installer:
	python scripts/build_installer.py

# ── Maintenance ───────────────────────────────────────────────────
health:
	python scripts/health_check_report.py

clean:
	if exist build rmdir /s /q build
	if exist dist rmdir /s /q dist
	if exist htmlcov rmdir /s /q htmlcov
	if exist .pytest_cache rmdir /s /q .pytest_cache
	if exist reports rmdir /s /q reports
	for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo "Cleaned build artifacts."

changelog:
	type CHANGELOG.md | more

autostart-on:
	python -m jarvis install-autostart

autostart-off:
	python -m jarvis uninstall-autostart

# ── Git shortcuts ─────────────────────────────────────────────────
push: format lint test
	git add -A
	git commit -m "$(m)"
	git push origin main
