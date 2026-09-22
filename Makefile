.PHONY: setup format lint-fix lint check test check-publish serve build package export-requirements

setup:
	uv sync --locked
	npm ci --ignore-scripts
	git config --local core.hooksPath .githooks

format:
	uv run --locked ruff format .
	npm run format

lint-fix:
	uv run --locked ruff check --fix .

lint:
	uv run --locked ruff check .

check: lint
	uv run --locked ruff format --check .
	npm run format:check
	uv run --locked pytest -q

test:
	uv run --locked pytest -q

check-publish:
	uv run --locked python scripts/check_publish.py

serve:
	uv run --locked python -m jevdocs serve

build:
	uv run --locked python -m jevdocs build

package:
	uv build
	uv run --locked python scripts/check_package.py

export-requirements:
	uv export --locked --no-dev --no-emit-project --no-hashes --output-file requirements.txt
