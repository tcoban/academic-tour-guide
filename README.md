# Academic Tour Guide

Academic Tour Guide is a full-stack internal tool for identifying high-value visiting speaker opportunities for KOF. It ingests seminar calendars, enriches researchers with biographic evidence, computes Zurich-specific opportunity scores, and prepares concierge-style outreach drafts.

## Monorepo Layout

- `backend/`: FastAPI API, SQLAlchemy models, scraping adapters, scheduling worker, and tests.
- `frontend/`: Next.js dashboard for the Daily Catch, trip clusters, calendar overlay, seminar administration, and outreach drafts.

## Backend Highlights

- PostgreSQL-ready SQLAlchemy schema with a SQLite fallback for local development.
- Rules-first source adapters for Bocconi, Mannheim, Bonn, ECB, BIS, and KOF.
- Evidence-backed enrichment for PhD institution and nationality facts.
- Availability engine that derives open seminar windows from recurring templates minus KOF occupied events and manual overrides.
- Opportunity scoring tuned to Zurich-specific alumni and DACH travel patterns.

## Frontend Highlights

- Daily Catch dashboard with clusters, calendar windows, and host-calendar context.
- Researcher detail view with evidence and itinerary context.
- Seminar template and override administration.
- Outreach draft preview for KOF admins.

## Local Development

### Backend

1. Create a virtual environment and install dependencies from `backend/pyproject.toml`.
2. Start the API with `uvicorn app.main:app --reload` from the `backend/` directory.
3. Optionally point `DATABASE_URL` to PostgreSQL. Without it, the app uses a local SQLite database file.

### Frontend

1. Install dependencies from `frontend/package.json`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to the backend URL if it differs from `http://localhost:8000`.
3. Run `npm run dev` from `frontend/`.

## Worker Commands

From `backend/`:

- `python -m app.worker ingest`
- `python -m app.worker sync-host`
- `python -m app.worker rebuild`

