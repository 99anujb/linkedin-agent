.PHONY: install test lint type dry-run

install:
	pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy src

dry-run:
	python -m agent draft --dry-run
