.PHONY: help install install-dev test lint format clean build freeze run

help:
	@echo "SamplePacker Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  install          Install package and dependencies"
	@echo "  install-dev      Install with dev dependencies"
	@echo "  test             Run tests"
	@echo "  lint             Run linters (ruff, mypy)"
	@echo "  format           Format code (black)"
	@echo "  clean            Remove build artifacts"
	@echo "  build            Build package"
	@echo "  freeze           Build PyInstaller onefile executable"
	@echo "  run              Run CLI with --help (smoke test)"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check samplepacker tests scripts
	mypy samplepacker --ignore-missing-imports || true

format:
	black samplepacker tests scripts

clean:
	rm -rf build/ dist/ *.egg-info/
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

build:
	python -m build

freeze:
	pyinstaller --onefile --name samplepacker-gui \
		--add-data "samplepacker/presets:presets" \
		samplepacker/gui/main.py
	@echo "Executable: dist/samplepacker-gui (or dist/samplepacker-gui.exe on Windows)"

run:
	python -m samplepacker.gui.main

