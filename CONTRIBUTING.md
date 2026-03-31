# Contributing to Jarvis

Thanks for your interest in contributing to Jarvis! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/GambaStudio/jarvis.git
cd jarvis
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,stt]"
```

## Code Style

- **Formatter/Linter:** Ruff (`ruff check . && ruff format .`)
- **Type hints** are required for all public functions
- **Docstrings** for all public modules, classes, and functions
- **Line length:** 100 characters max

## Branching

- `main` — stable, release-ready
- `develop` — next release integration
- `feat/xxx` — feature branches
- `fix/xxx` — bug fix branches

## Pull Requests

1. Fork the repo and create your branch from `develop`
2. Write tests for new functionality
3. Ensure `ruff check .` and `pytest` pass
4. Update CHANGELOG.md with your changes
5. Open a PR with a clear description

## Adding Pipeline Components

Want to add a new STT, TTS, or Wake Word engine?

1. Create a new file in the appropriate `src/jarvis/pipeline/` subdirectory
2. Implement the abstract interface from `base.py`
3. Add the engine to the config options
4. Add tests
5. Document in README

## Adding Skills

Skills are Markdown files in the `skills/` directory. No core code review needed — submit to the [jarvis-skills](https://github.com/GambaStudio/jarvis-skills) repository.

## Code of Conduct

Be respectful, constructive, and inclusive. We're building something cool together.
