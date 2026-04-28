# Academic Tour Guide

Academic Tour Guide is a full-stack internal tool for identifying high-value visiting speaker opportunities for KOF. It ingests seminar calendars, enriches researchers with biographic evidence, computes Zurich-specific opportunity scores, and prepares concierge-style outreach drafts.

## Monorepo Layout

- `backend/`: FastAPI API, SQLAlchemy models, scraping adapters, scheduling worker, and tests.
- `frontend/`: Next.js dashboard for the Daily Catch, trip clusters, calendar overlay, seminar administration, and outreach drafts.

## Backend Highlights

- PostgreSQL-ready SQLAlchemy schema with a SQLite fallback for local development.
- Alembic baseline migration for repeatable PostgreSQL or SQLite schema setup.
- Rules-first source adapters for Bocconi, Mannheim, Bonn, ECB, BIS, and KOF.
- KOF host-calendar sync reads the ETH public calendar JSON feed discovered from the KOF event page and stores those entries as occupied slots.
- BIS adapter reads a public call-for-papers PDF and extracts named academic keynote speakers as Basel opportunity signals.
- RePEc/IDEAS identity sync with persistent external researcher identities.
- Institution-linked document discovery for seminar pages, RePEc profiles, public profile pages, CVs, and PDFs.
- Evidence-backed enrichment with pending fact candidates, approved facts, source documents, and review history.
- Availability engine that derives open seminar windows from recurring templates minus KOF occupied events and manual overrides.
- Cost-sharing calculator that compares a standalone Zurich round trip with a Zurich add-on from the existing European itinerary.
- Opportunity scoring tuned to Zurich-specific alumni and DACH travel patterns, with explicit flags when a score uses unreviewed evidence.
- Opportunity workbench API that matches ranked trip clusters to the best open KOF slot and exposes draft-readiness blockers.
- Outreach draft generation gated on approved biographic evidence, checklist review, and optional API token protection.

## Frontend Highlights

- Daily Catch dashboard with clusters, calendar windows, and host-calendar context.
- Researcher detail view with approved facts, pending evidence, source documents, identities, and itinerary context.
- Daily Operator Runbook that summarizes source attention, pending evidence, open KOF windows, draft-ready opportunities, and draft lifecycle follow-up.
- Golden Window calendar that overlays KOF occupied events, derived open slots, and matched opportunity candidates.
- Manual approved-fact entry on researcher dossiers for admins to unblock draft eligibility with auditable source notes.
- Researcher-scoped refresh controls for RePEc identity sync and biographer document/fact extraction.
- Review inbox for filtering, editing, approving, rejecting, and auditing extracted fact candidates before outreach.
- Seminar template and override administration with create, edit, and delete controls.
- Opportunity workbench for ranking trip clusters, inspecting best KOF slot fit, and seeing whether outreach is draft-ready.
- Cost-sharing estimates on opportunity cards and draft previews.
- Draft library for browsing generated outreach variants, filtering by lifecycle status, and reopening provenance-backed draft previews.
- Source health page for checking live scraper output, recording audit history, spotting zero-event sources, and surfacing reliability trends.
- Outreach draft preview for KOF admins with template selection, approved-fact provenance, send brief, checklist-gated lifecycle status actions, copy, and text export.
- Optional Basic Auth protection for the frontend and API token protection for the backend.

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

## Production Readiness

- Set `ATG_APP_PASSWORD` to protect the frontend with Basic Auth.
- Set `ATG_API_ACCESS_TOKEN` and matching `NEXT_PUBLIC_API_ACCESS_TOKEN` to require an API token on backend calls.
- GitHub Actions CI runs backend tests and the frontend production build on pushes and pull requests.
- The scheduled worker workflow runs `audit-sources` on weekday mornings and can run other worker commands manually.

## Worker Commands

From `backend/`:

- `python -m app.worker ingest`
- `python -m app.worker sync-host`
- `python -m app.worker repec-sync`
- `python -m app.worker biographer-refresh`
- `python -m app.worker seed-demo`
- `python -m app.worker rebuild`
- `python -m app.worker audit-sources`

`audit-sources` records the current source-health snapshot in the local database and prints the same summary to the terminal.

## Demo Data

For a local pilot demo, run:

```bash
python -m alembic upgrade head
python -m app.worker seed-demo
```

This creates a small deterministic dataset with approved facts, pending fact candidates, source documents, RePEc identities, trip clusters, and KOF seminar availability.

If your local `backend/academic_tour_guide.db` was created before migrations were added, move it aside first and rerun the two commands above. The SQLite database is local-only and ignored by Git.

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
- `GET /api/opportunities/workbench`
- `GET /api/operator/runbook`
- `GET /api/outreach-drafts`
- `PATCH /api/outreach-drafts/{id}/status`
- `GET /api/source-health`
- `POST /api/jobs/audit-sources`
- `GET /api/source-health/history`
- `GET /api/source-health/reliability`

PDF extraction is enabled through `pypdf`; unsupported or failed documents are recorded as source documents without crashing the refresh pipeline.
