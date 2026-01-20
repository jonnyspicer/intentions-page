# CLAUDE.md

## Project Overview

This is a Django application for tracking intentions.

## Development Commands

### Running Tests

```bash
pytest
```

### Running Linters

Before committing any changes, run all linters and fix any errors:

```bash
# Code formatting
black .

# Import sorting
isort .

# Linting
flake8

# Type checking
mypy intentions_page
```

Or run all checks via pre-commit:

```bash
pre-commit run --all-files
```

### Pre-commit Requirement

Always run tests and linters before committing. Fix all errors before creating commits.
