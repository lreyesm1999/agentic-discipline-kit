.PHONY: install test lint format typecheck coverage check build doctor clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy src

coverage:
	pytest --cov=agentic_discipline --cov-report=term-missing --cov-report=xml --cov-report=json:coverage.json
	python scripts/coverage_gate.py --report coverage.json --min-line 90 --min-branch 85

check: lint typecheck coverage
	python scripts/repo_check.py
	python -m agentic_discipline doctor

build:
	python -m build

doctor:
	python -m agentic_discipline doctor

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in map(pathlib.Path, ['build','dist','.pytest_cache','.mypy_cache','.ruff_cache','htmlcov'])]"
