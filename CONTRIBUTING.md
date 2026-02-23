# Contributing to Annal

Thanks for your interest in Annal! This project is maintained by a single developer, so the contribution process is designed to keep things manageable while still being welcoming.

## How to contribute

### Bug reports and feature requests

Open a GitHub issue. Include enough context to reproduce the problem or understand the idea. For bugs, include the Python version, OS, backend (ChromaDB or Qdrant), and any error output.

### Code contributions

Please open an issue before writing code. This lets us align on whether the change fits the project direction and agree on an approach before you invest time. Small fixes (typos, doc corrections) can go straight to a PR.

Once we've agreed on an approach:

1. Fork the repo and create a branch from `main`
2. Install the dev environment: `pip install -e ".[dev]"`
3. Write tests for your changes — run `pytest -v` and make sure everything passes
4. Open a PR referencing the issue

### Areas where help is welcome

If you're looking for something to work on, these are areas where contributions would be particularly valuable:

- Windows service automation (the `annal install` flow on Windows currently requires manual setup)
- Documentation improvements and troubleshooting guides
- Additional vector backend plugins (implementing the `VectorBackend` protocol)
- Dashboard UI improvements
- Bug reports from real-world usage across different environments

## Code standards

- Type hints on all function signatures
- Tests for new functionality (the project follows TDD)
- No `print()` to stdout — it breaks MCP stdio transport. Use `logging` to stderr
- Python 3.11+

## Development setup

```bash
git clone https://github.com/heyhayes/annal.git
cd annal
pip install -e ".[dev]"
pytest -v
```

To test with Qdrant (optional): `pip install -e ".[dev,qdrant]"` and have a Qdrant instance running at `localhost:6333`.

## Questions?

Open an issue or start a discussion. There are no bad questions.
