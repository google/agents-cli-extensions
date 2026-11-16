.PHONY: install test lint lint-check lint-templates lock-check

TEMPLATES := $(wildcard core/*/template)

# Template code is end-user code copied into generated projects, so it carries no header.
ADDLICENSE := go run github.com/google/addlicense@v1.2.0 -c "Google LLC" -l apache -y 2026 \
	-ignore 'core/*/template/**' -ignore pyproject.toml

install:
	uv sync --locked

test:
	uv run pytest

lint:
	uv run ruff check . --fix
	uv run ruff format .
	git ls-files | xargs $(ADDLICENSE)

lint-check:
	uv run ruff check .
	uv run ruff format --check .
	git ls-files | xargs $(ADDLICENSE) -check

# Lint each template the way a scaffolded project does, or `agents-cli lint`
# fails on a fresh scaffold.
lint-templates:
	for tmpl in $(TEMPLATES); do \
		uv run ruff format --check --line-length 88 "$$tmpl" && \
		uv run ruff check --line-length 88 "$$tmpl" || exit 1; \
	done

# Each template's uv.lock is copied into generated projects as-is.
lock-check:
	for tmpl in $(TEMPLATES); do \
		(cd "$$tmpl" && uv lock --check) || exit 1; \
	done
