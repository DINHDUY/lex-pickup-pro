# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- Initial project documentation and contributor guidance.
- Root-level automation with `make` targets for setup, development, linting, testing, and build workflows.
- MIT license and open-source project metadata.
- CI builds backend and frontend container images and publishes them to GitHub Container Registry from the default branch and `v*` tags.

### Changed
- Standardized local development commands around Docker Compose, backend `uv`, and frontend `npm` scripts.
- CI no longer runs the PostgreSQL service job or the Cosmos emulator job; image publish waits only on the main verify job.

## [0.1.0] - 2026-09-13

### Added
- Full-stack club platform with FastAPI backend and React/Vite frontend.
- Match scheduling, RSVPs, lineups, analytics, club management, and player import workflows.
- PostgreSQL-backed data model with Alembic migrations and demo seeding.
- Playwright end-to-end test coverage and CI-oriented verification steps.
- Docker Compose setup for local demo and deployment workflows.
