.DEFAULT_GOAL := help
.PHONY: help install format lint types test verify build

help: ## List commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install dependencies from the lock file
	uv sync --locked

format: ## Fix formatting and autofixable lint issues
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Check formatting and lint
	uv run ruff format --check .
	uv run ruff check .

types: ## Type-check with mypy
	uv run mypy

test: ## Run tests
	uv run pytest

verify: lint types test ## Everything CI runs

build: ## Build the wheel and sdist into dist/ and check their metadata
	rm -rf dist
	uv build
	uv run twine check --strict dist/*
