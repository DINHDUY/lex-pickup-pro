# Contributing

Thanks for your interest in contributing to Lex Pickup Pro.

## Development setup

1. Install the required tooling:
   - Node.js 22.12+ or later
   - `uv` for Python environment management
   - Docker with Compose for the demo stack
2. Install dependencies:

```bash
make install
```

3. Initialize the backend environment and demo database:

```bash
make setup
```

4. Start the app locally:

```bash
make dev
```

The frontend runs on http://localhost:5173 and the backend is available at http://127.0.0.1:8000.

## Project workflow

- Backend code lives in `backend/app`.
- Frontend code lives in `frontend/src`.
- Database migrations live under `backend/alembic/versions`.
- Browser tests live under `frontend/e2e`.

## Running checks

Before opening a pull request, run:

```bash
make lint
make test
make check
```

You can also run targeted commands directly:

```bash
cd backend
uv run ruff check app tests
uv run pytest -q
uv run alembic check

cd frontend
npm run lint
npm run build
npm run test:e2e
```

## Pull request guidance

- Keep changes focused and easy to review.
- Include tests for behavioral or regression fixes when practical.
- Update the changelog for user-visible changes.
- Keep commit messages clear and specific.
- If you change database behavior, include the migration and note the impact.

## Reporting issues

Please file issues with:

- a clear description of the problem
- reproduction steps or screenshots when useful
- environment details (OS, browser, versions)
- any relevant logs or error output

## Code of conduct

This project is intended to be a welcoming and professional place for collaboration. Please be respectful, constructive, and solution-oriented in discussions and contributions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
