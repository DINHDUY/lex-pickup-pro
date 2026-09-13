# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- Azure Container Apps deployment scaffolding for a Cosmos DB-only production deployment.
- GHCR-based container image publishing and deployment workflow for backend and frontend services.
- Provider-neutral storage abstraction with SQL and Cosmos adapters, plus migration and recovery tooling.
- Cosmos-specific document model, command receipts, and recovery support for club data.
- Production-oriented configuration guards for secure deployment settings and explicit environment validation.

### Changed
- Reframed the deployment architecture around Azure Cosmos DB for NoSQL instead of PostgreSQL.
- Updated deployment and environment documentation to describe the Azure Container Apps release flow.
- Kept the local Docker demo paths while separating them from the real Azure deployment configuration.

## [0.1.0] - 2026-09-13

### Added
- Full-stack club platform with FastAPI backend and React/Vite frontend.
- Match scheduling, RSVPs, lineups, analytics, club management, and player import workflows.
- Cosmos DB support alongside the default SQL provider, including provider abstraction and migration tooling.
- Playwright end-to-end test coverage and CI-oriented verification steps.
- Docker Compose setup for local demo and deployment workflows.
- GitHub Container Registry publishing for backend and frontend container images.

### Changed
- Standardized local development around backend `uv` and frontend `npm` scripts.
- Clarified deployment guidance for production use, including HTTPS, secure cookies, and explicit configuration checks.
- Refined the real-club import and seeding flow to separate demo data from production club data.
