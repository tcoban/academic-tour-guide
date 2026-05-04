# Roadshow

Roadshow is a KOF-first academic tour concierge for identifying high-value visiting speaker opportunities, modeling Zurich as a smart tour stop, and preparing evidence-backed outreach. It keeps the current KOF workflow as the center of gravity while adding speaker preferences, wishlist alerts, tour-leg proposals, relationship memory, feedback signals, and auditable decision events.

## Monorepo Layout

- `backend/`: FastAPI API, SQLAlchemy models, scraping adapters, scheduling worker, and tests.
- `frontend/`: Next.js dashboard for the Daily Catch, Roadshow wishlist, tour legs, calendar overlay, seminar administration, and outreach drafts.

## Backend Highlights

- PostgreSQL-ready SQLAlchemy schema with a SQLite fallback for local development.
- Alembic baseline migration for repeatable PostgreSQL or SQLite schema setup.
- Rules-first source adapters for Bocconi, Mannheim, Bonn, BIS, and KOF, plus a source registry for ECB, LSE, PSE, Oxford, TSE, LMU Munich, Goethe Frankfurt, UZH, ETH, SNB, Bank of England, BSE, Carlos III Madrid, and EUI.
- KOF host-calendar sync reads the ETH public calendar JSON feed discovered from the KOF event page and stores those entries as occupied slots.
- BIS adapter reads a public call-for-papers PDF and extracts named academic keynote speakers as Basel opportunity signals.
- RePEc/IDEAS identity sync with persistent external researcher identities.
- Institution-linked document discovery for seminar pages, RePEc profiles, public profile pages, CVs, and PDFs.
- Evidence-backed enrichment with pending fact candidates, approved facts, source documents, and review history.
- Availability engine that derives open seminar windows from recurring templates minus KOF occupied events and manual overrides.
- Cost-sharing and rail-price checker for internal first-class/full-fare planning, with auditable live/cached/fallback fare provenance.
- Roadshow models for speaker profiles, institution profiles, wishlist entries, wishlist alerts, tour legs, tour stops, relationship briefs, feedback signals, and audit events.
- Negotiator-lite service that proposes deterministic KOF tour legs without contracts, payment, or live travel booking.
- Opportunity scoring tuned to Zurich-specific alumni and DACH travel patterns, with explicit flags when a score uses unreviewed evidence.
- Opportunity workbench API that matches ranked trip clusters to the best open KOF slot and exposes draft-readiness blockers.
- Relations Manager-style outreach draft generation gated on approved biographic evidence, enriched with relationship memory and speaker preference/rider checks.

## Frontend Highlights

- Daily Catch dashboard with clusters, calendar windows, and host-calendar context.
- Speaker dossier view with approved facts, pending evidence, source documents, identities, Roadshow preferences, relationship memory, and itinerary context.
- KOF wishlist page for speaker/topic watch entries and Scout-generated alerts.
- Tour-leg ledger and proposal detail pages for deterministic cost-split review.
- Daily Operator Runbook that summarizes source attention, pending evidence, open KOF windows, draft-ready opportunities, and draft lifecycle follow-up.
- Golden Window calendar that overlays KOF occupied events, derived open slots, and matched opportunity candidates.
- Manual approved-fact entry on researcher dossiers for admins to unblock draft eligibility with auditable source notes.
- Researcher-scoped refresh controls for RePEc identity sync and biographer document/fact extraction.
- Review inbox for filtering, editing, approving, rejecting, and auditing extracted fact candidates before outreach.
- Seminar template and override administration with create, edit, and delete controls.
- Opportunity workbench for ranking trip clusters, inspecting best KOF slot fit, and seeing whether outreach is draft-ready.
- Cost-sharing estimates on opportunity cards and draft previews.
- Draft library for browsing generated outreach variants, filtering by lifecycle status, and reopening provenance-backed draft previews.
- Data Sources page for checking live scraper output, recording audit history, spotting zero-event sources, and surfacing reliability trends.
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
2. Set `NEXT_PUBLIC_API_BASE_URL` to the backend URL if it differs from `http://127.0.0.1:8000`.
3. Run `npm run dev` from `frontend/`.

## Production Readiness

- Set `ROADSHOW_ENV=production` for the internal protected pilot.
- Production mode requires `ROADSHOW_APP_PASSWORD` for frontend Basic Auth and `ROADSHOW_API_ACCESS_TOKEN` with matching `NEXT_PUBLIC_ROADSHOW_API_ACCESS_TOKEN` for backend API calls.
- The older `ATG_*` names remain supported for transition environments.
- Keep `ROADSHOW_ENABLE_DEMO_TOOLS=false` in production. The API seed endpoint is unavailable unless this flag is explicitly enabled.
- Rail planning defaults to `ROADSHOW_RAIL_CLASS=first` and `ROADSHOW_RAIL_FARE_POLICY=full_fare`; configure `OPENTRANSPORTDATA_API_TOKEN` or Rail Europe ERA credentials for authorized live fare providers.
- GitHub Actions CI runs backend tests and the frontend production build on pushes and pull requests.
- The scheduled worker workflow runs `audit-sources` on weekday mornings and can run other worker commands manually.

## Worker Commands

From `backend/`:

- `python -m app.worker ingest`
- `python -m app.worker real-sync`
- `python -m app.worker sync-host`
- `python -m app.worker repec-sync`
- `python -m app.worker biographer-refresh`
- `python -m app.worker seed-demo` (development only)
- `python -m app.worker rebuild`
- `python -m app.worker audit-sources`

`audit-sources` records the current source-health snapshot in the local database and prints the same summary to the terminal.

## Development-Only Seed Data

For parser tests, screenshots, or offline workflow checks, enable development seed tooling and run:

```bash
python -m alembic upgrade head
set ROADSHOW_ENABLE_DEMO_TOOLS=true
python -m app.worker seed-demo
```

This creates a small deterministic dataset with approved facts, pending fact candidates, source documents, RePEc identities, trip clusters, KOF seminar availability, a Roadshow wishlist entry, relationship memory, and one proposed tour leg. It is not part of normal operation.

If your local `backend/academic_tour_guide.db` was created before migrations were added, move it aside first and rerun the two commands above. The SQLite database is local-only and ignored by Git.

## Phase 2 Biographer Flow

1. Run `python -m app.worker audit-sources` or the Start-page real source sync to check the expanded watchlist and record source status.
2. Run `python -m app.worker ingest` to collect external speaker appearances from production-ready adapters.
3. Run `python -m app.worker biographer-refresh` to sync RePEc identities, fetch institution-linked documents, and extract fact candidates.
4. Open the frontend review queue at `/review` and approve or reject pending evidence.
5. Generate outreach drafts only after the required PhD institution and nationality facts are approved.

Useful API endpoints:

- `POST /api/jobs/repec-sync`
- `POST /api/jobs/biographer-refresh`
- `POST /api/jobs/seed-demo` (development only, behind `ROADSHOW_ENABLE_DEMO_TOOLS=true`)
- `GET /api/review/facts`
- `POST /api/review/facts/{id}/approve`
- `POST /api/review/facts/{id}/reject`
- `GET /api/researchers/{id}/documents`
- `GET/PATCH /api/speakers/{id}/profile`
- `GET/PATCH /api/institutions/{id}/profile`
- `GET/POST/PATCH/DELETE /api/wishlist`
- `GET /api/wishlist-alerts`
- `POST /api/tour-legs/propose`
- `GET /api/tour-legs`
- `GET /api/tour-legs/{id}`
- `GET/PATCH /api/relationship-briefs/{speaker_id}/{institution_id}`
- `POST /api/feedback-signals`
- `GET /api/audit-events`
- `GET /api/opportunities/workbench`
- `GET /api/operator/runbook`
- `GET /api/outreach-drafts`
- `PATCH /api/outreach-drafts/{id}/status`
- `GET /api/source-health`
- `POST /api/jobs/audit-sources`
- `GET /api/source-health/history`
- `GET /api/source-health/reliability`

PDF extraction is enabled through `pypdf`; unsupported or failed documents are recorded as source documents without crashing the refresh pipeline.
