# Roadshow

Roadshow is a multi-tenant, self-service SaaS platform for academic seminar teams. It helps institutions discover speaker travel opportunities, evaluate research fit, plan sensible host stops, audit evidence, and prepare professional invitation drafts. KOF Swiss Economic Institute remains the first seeded tenant and regression workflow, but the product now supports additional institutions with their own location, research priorities, slots, wishlist, policies, and private operational data.

## Monorepo Layout

- `backend/`: FastAPI API, SQLAlchemy models, Alembic migrations, source adapters, worker commands, and tests.
- `frontend/`: Next.js application for the guided Start flow, opportunities, calendar, evidence review, drafts, tenant settings, and Roadshow operations.

## Backend Highlights

- Multi-tenant core with `Tenant`, `User`, `TenantMembership`, and `TenantSettings`.
- Email/password authentication with HTTP-only session cookies and tenant switching for users with multiple memberships.
- Shared public intelligence for researchers, identities, source documents, public talk events, and global trip clusters.
- Tenant-scoped operational data for host calendars, seminar slot templates, open windows, wishlist entries, alerts, drafts, tour legs, relationship memory, feedback, audit events, and business-case runs.
- Alembic-backed schema setup with a default KOF tenant/backfill path for existing local data.
- Rules-first source adapters for Bocconi, Mannheim, Bonn, BIS, KOF, and an expanded source registry for ECB, LSE, PSE, Oxford, TSE, LMU Munich, Goethe Frankfurt, UZH, ETH, SNB, Bank of England, BSE, Carlos III Madrid, and EUI.
- RePEc/IDEAS identity sync, institution-linked document discovery, CV/PDF extraction, and evidence-backed fact review.
- Tenant-aware availability, scoring, research-fit, route plausibility, rail pricing, cost split, wishlist matching, and anonymous opt-in tour assembly.
- Outreach draft generation gated on approved evidence and locked to the same best slot selected by `OpportunityWorkbench.best_window_for_cluster()`.

## Frontend Highlights

- Guided Start page that shows the next operational action for the active tenant.
- Register, login, logout, and tenant settings screens for self-service onboarding.
- Tenant-aware opportunities, host calendar, evidence inbox, drafts, data sources, wishlist, tour legs, and business-case audit surfaces.
- Actionable-warning pattern: blocker/warning states should provide a direct resolving action or link to the exact workspace that resolves the issue.
- Draft flow creates one professional host invitation draft for a normal opportunity; logistics and cost rationale stay internal.
- Anonymous co-host matching masks other institutions unless the opt-in workflow permits disclosure.

## Local Development

### Backend

1. Create a virtual environment and install dependencies from `backend/pyproject.toml`.
2. Run `python -m alembic upgrade head` from `backend/` to apply migrations.
3. Start the API with `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from `backend/`.
4. Optionally set `DATABASE_URL` to PostgreSQL. Without it, Roadshow uses a local SQLite database file.

### Frontend

1. Install dependencies from `frontend/package.json`.
2. Set `NEXT_PUBLIC_API_BASE_URL` if the backend differs from `http://127.0.0.1:8000/api`.
3. Run `npm run dev` from `frontend/`.
4. Open `/register` to create the first user, tenant, host institution, and owner membership, or use the seeded KOF/default tenant in development workflows.

## Production Readiness

- Set `ROADSHOW_ENV=production` for protected deployments.
- The frontend redirects unauthenticated production users to `/login` and uses the `roadshow_session` HTTP-only cookie after login.
- The backend exposes email/password session endpoints and tenant context. Configure `ROADSHOW_API_ACCESS_TOKEN` only when an additional edge/API token gate is desired; clients then send it as `x-roadshow-api-key`.
- Keep `ROADSHOW_ENABLE_DEMO_TOOLS=false` in production. The seed endpoint is unavailable unless this flag is explicitly enabled.
- Rail planning defaults to `ROADSHOW_RAIL_CLASS=first` and `ROADSHOW_RAIL_FARE_POLICY=full_fare`; configure `OPENTRANSPORTDATA_API_TOKEN` or Rail Europe ERA credentials for authorized live fare providers.
- The older `ATG_*` names remain supported only for transition environments.
- GitHub Actions CI runs backend tests and the frontend production build on pushes and pull requests.

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

`real-sync` runs the deterministic operational pipeline. `audit-sources` records source-health snapshots and prints the same summary to the terminal.

## Development-Only Seed Data

For parser tests, screenshots, or offline workflow checks, enable development seed tooling and run:

```bash
python -m alembic upgrade head
set ROADSHOW_ENABLE_DEMO_TOOLS=true
python -m app.worker seed-demo
```

This creates deterministic local data with approved facts, pending fact candidates, source documents, RePEc identities, trip clusters, KOF seminar availability, a Roadshow wishlist entry, relationship memory, and one proposed tour leg. It is not part of normal operation.

## Key API Surfaces

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `GET/PATCH /api/tenants/current`
- `GET/PATCH /api/tenants/current/settings`
- `POST /api/tenants/switch`
- `POST /api/operator/real-sync`
- `GET /api/operator/cockpit`
- `GET /api/tenant/opportunities`
- `GET /api/opportunities/workbench`
- `GET /api/calendar/overlay`
- `GET/POST/PATCH/DELETE /api/wishlist`
- `POST /api/wishlist-matches/refresh`
- `GET /api/wishlist-matches`
- `POST /api/tour-assemblies/propose`
- `GET /api/tour-assemblies`
- `POST /api/travel-price-checks`
- `POST /api/tour-legs/{id}/refresh-prices`
- `GET /api/review/facts`
- `POST /api/review/facts/{id}/approve`
- `POST /api/review/facts/{id}/reject`
- `GET /api/outreach-drafts`
- `PATCH /api/outreach-drafts/{id}/status`
- `POST /api/business-cases/run`
- `GET /api/business-cases/runs`

## Release Discipline

- Every commit that changes product behavior must update `RELEASE_NOTES.md` and the relevant version metadata, or explicitly include `no release-note impact` in the commit message.
- Release commits must keep backend and frontend versions aligned, update `RELEASE_NOTES.md`, run backend tests, frontend smoke checks, frontend production build, and Alembic head validation.
- Releases use annotated Git tags in the form `vX.Y.Z`.

## Release Notes

See `RELEASE_NOTES.md`.
