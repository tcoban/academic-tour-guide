# Academic Tour Guide

Academic Tour Guide is a full-stack internal tool for identifying high-value visiting speaker opportunities for KOF. It ingests seminar calendars, enriches researchers with biographic evidence, computes Zurich-specific opportunity scores, and prepares concierge-style outreach drafts.

## Monorepo Layout

- `backend/`: FastAPI API, SQLAlchemy models, scraping adapters, scheduling worker, and tests.
- `frontend/`: Next.js dashboard for the Daily Catch, trip clusters, calendar overlay, seminar administration, and outreach drafts.

## Backend Highlights

- PostgreSQL-ready SQLAlchemy schema with a SQLite fallback for local development.
- Alembic baseline migration for repeatable PostgreSQL or SQLite schema setup.
- Rules-first source adapters for Bocconi, Mannheim, Bonn, ECB, BIS, and KOF.
- RePEc/IDEAS identity sync with persistent external researcher identities.
- Institution-linked document discovery for seminar pages, RePEc profiles, public profile pages, CVs, and PDFs.
- Evidence-backed enrichment with pending fact candidates, approved facts, source documents, and review history.
- Availability engine that derives open seminar windows from recurring templates minus KOF occupied events and manual overrides.
- Opportunity scoring tuned to Zurich-specific alumni and DACH travel patterns, with explicit flags when a score uses unreviewed evidence.
- Outreach draft generation gated on approved biographic evidence.

## Frontend Highlights

- Daily Catch dashboard with clusters, calendar windows, and host-calendar context.
- Researcher detail view with approved facts, pending evidence, source documents, identities, and itinerary context.
- Review inbox for approving or rejecting extracted fact candidates before outreach.
- Seminar template and override administration.
- Outreach draft preview for KOF admins.

## Local Development

### Backend

1. Create a virtual environment and install dependencies from `backend/pyproject.toml`.
2. Run `python -m alembic upgrade head` from `backend/` to apply migrations.
3. Start the API with `uvicorn app.main:app --reload` from the `backend/` directory.
4. Optionally point `DATABASE_URL` to PostgreSQL. Without it, the app uses a local SQLite database file.

### Frontend

1. Install dependencies from `frontend/package.json`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to the backend URL if it differs from `http://localhost:8000`.
3. Run `npm run dev` from `frontend/`.

## Worker Commands

From `backend/`:

- `python -m app.worker ingest`
- `python -m app.worker sync-host`
- `python -m app.worker repec-sync`
- `python -m app.worker biographer-refresh`
- `python -m app.worker seed-demo`
- `python -m app.worker rebuild`

## Demo Data

For a local pilot demo, run:

```bash
python -m alembic upgrade head
python -m app.worker seed-demo
```

This creates a small deterministic dataset with approved facts, pending fact candidates, source documents, RePEc identities, trip clusters, and KOF seminar availability.

## Phase 2 Biographer Flow

1. Run `python -m app.worker ingest` to collect external speaker appearances.
2. Run `python -m app.worker biographer-refresh` to sync RePEc identities, fetch institution-linked documents, and extract fact candidates.
3. Open the frontend review queue at `/review` and approve or reject pending evidence.
4. Generate outreach drafts only after the required PhD institution and nationality facts are approved.

Useful API endpoints:

- `POST /api/jobs/repec-sync`
- `POST /api/jobs/biographer-refresh`
- `POST /api/jobs/seed-demo`
- `GET /api/review/facts`
- `POST /api/review/facts/{id}/approve`
- `POST /api/review/facts/{id}/reject`
- `GET /api/researchers/{id}/documents`

PDF extraction is enabled through `pypdf`; unsupported or failed documents are recorded as source documents without crashing the refresh pipeline.
