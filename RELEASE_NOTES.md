# Release Notes

## v0.3.4 - 2026-05-04

### Fixed

- Cloud Build frontend and backend templates now use an explicit `_IMAGE_TAG` substitution instead of `$SHORT_SHA`, preventing invalid image names during manual Cloud Shell builds.

### Changed

- `deploy_frontend.sh` now derives an image tag from the current Git commit, or from `IMAGE_TAG` when provided, and passes it to Cloud Build.
- Backend and frontend package versions are aligned at `0.3.4`.

### Operations

- README frontend deployment guidance now documents `_IMAGE_TAG` for manual Cloud Build submissions.

## v0.3.3 - 2026-05-04

### Added

- Hardened `deploy_frontend.sh` helper for Google Cloud Shell frontend deployment.
- Deployment checks for active gcloud auth, required APIs, Artifact Registry repository, backend service URL, and existing `roadshow-api-access-token` Secret Manager secret.
- Secret-level IAM binding so the Cloud Run runtime service account can read the backend API token.
- README guidance for the recommended frontend Cloud Run deployment path and manual fallback commands.

### Changed

- Backend and frontend package versions are aligned at `0.3.3`.
- Frontend deployment now prefers reusing the existing API-token secret rather than creating or rotating it during every deploy.

### Security

- The deployment helper does not hardcode, print, create, or overwrite the backend API token.

## v0.3.2 - 2026-05-04

### Added

- Same-origin Next.js proxy at `/api/roadshow/*` for `roadshow-frontend`, forwarding cookies and adding the backend API token server-side.
- Cloud Build frontend deployment template for the separate `roadshow-frontend` Cloud Run service.
- Server-side API wrapper that forwards `roadshow_session` cookies during server-rendered page data loads.
- Smoke checks that keep backend API tokens out of `NEXT_PUBLIC_*` browser configuration.

### Changed

- Backend and frontend package versions are aligned at `0.3.2`.
- Frontend production builds now default to `NEXT_PUBLIC_API_BASE_URL=/api/roadshow`.
- Docker Compose routes the frontend through the same proxy path while using the backend service name internally.

### Security

- `ROADSHOW_API_ACCESS_TOKEN` is now consumed by the frontend server proxy, not by browser-bundled frontend code.

## v0.3.1 - 2026-05-04

### Added

- Cloud Build backend deployment template for `roadshow-backend`, including Docker image build/push, a Cloud Run migration job, and Cloud Run service deployment.
- Production Dockerfile for `roadshow-frontend`, using `npm ci`, `npm run build`, and `next start` on the dynamic Cloud Run `PORT`.
- Docker ignore files so local databases, build output, caches, and Node modules stay out of image contexts.
- CI Docker build checks for both backend and frontend images.

### Changed

- Backend and frontend package versions are aligned at `0.3.1`.
- Docker Compose now maps the backend container's Cloud Run-style port `8080` to local `8000`, and serves the frontend production container on local `3000`.
- Backend production startup now expects Alembic-managed schema rather than calling `create_all()` on every app boot.

### Security

- `ROADSHOW_ENV=production` now validates that PostgreSQL/Cloud SQL `DATABASE_URL`, `ROADSHOW_CORS_ORIGINS`, secure session cookies, disabled demo tools, and either `ROADSHOW_API_ACCESS_TOKEN` or `ROADSHOW_CLOUD_IAP_ENABLED=true` are configured.
- Production session cookies are `Secure` by default, while development remains usable over local HTTP.
- Anonymous default-tenant fallback is blocked for protected production API calls.

### Operations

- GitHub repository health remains green on `main`; the remaining cloud-readiness work is now frontend deployment wiring, Cloud SQL secret creation, and GitHub branch-protection/release-object administration.

## v0.3.0 - 2026-05-04

### Added

- Controlled Roadshow AI service on top of Vertex AI/Gemini with JSON-only calls, feature flags, timeout handling, provider fallback, and tenant-scoped audit events.
- AI Evidence Assistant that reads stored trusted source-document text and creates pending `FactCandidate` records with source snippets and provenance.
- AI Research-Fit Explainer that appends a zero-point rationale block without changing deterministic opportunity scores.
- AI-assisted invitation body generation behind the existing approved-fact and best-slot draft gate.
- AI Autopilot Planner that can suggest only backend-validated actions from the current operator cockpit.
- Frontend actions for AI evidence search, AI research-fit explanation, AI-assisted draft creation, and AI next-action planning.

### Changed

- Backend and frontend package versions are aligned at `0.3.0`.
- Normal outreach drafts still use deterministic send briefs, route/cost context, and slot selection; AI can only replace the visible email body after validation.
- Review inbox copy now identifies candidates suggested by AI from source documents.

### Safety

- AI never auto-approves facts, never changes score points, never creates costs or fares, and never bypasses deterministic route, slot, or outreach gates.
- AI draft validation rejects money/fare/savings language, unsupported Europe-visit phrasing, and bodies that omit the selected seminar slot.
- Invalid AI autopilot suggestions are hidden and replaced by Roadshow's deterministic next action.

## v0.2.1 - 2026-05-04

### Added

- Central Vertex AI/Gemini adapter using `google-cloud-aiplatform`, `vertexai.init(project="kof-gcloud", location="europe-west6")`, and `GenerativeModel`.
- Static safety tests that keep Gemini API-key usage out of backend application code.

### Changed

- Backend Dockerfile now targets Cloud Run by binding Uvicorn to the dynamic `PORT` environment variable, defaulting to `8080`.
- Backend dependencies now include `google-cloud-aiplatform`; `uvicorn` remains explicit.
- Backend and frontend package versions are aligned at `0.2.1`.

### Security

- Vertex AI is prepared for Application Default Credentials through the Cloud Run service account. No Gemini API keys are used or introduced.

## v0.2.0 - 2026-05-04

### Added

- Multi-tenant SaaS foundation with tenants, users, memberships, tenant settings, and active tenant context.
- Self-service registration and email/password login backed by HTTP-only Roadshow session cookies.
- Tenant-scoped operational data for host calendars, slot templates, overrides, open windows, wishlist entries, alerts, drafts, tour legs, relationship briefs, feedback signals, audit events, and business-case runs.
- Tenant-aware settings UI for host profile, research priorities, hospitality policy, rail policy, source subscriptions, and anonymous matching opt-in.
- Anonymous opt-in co-host matching and tour assembly primitives that mask neighboring institutions by default.
- Alembic migration for the multi-tenant schema and default KOF tenant backfill.
- Release discipline documented in the README.

### Changed

- Roadshow is now documented as a self-service multi-tenant platform rather than a KOF-only internal tool.
- Scoring, availability, source sync, drafts, and operational workbench flows use tenant context while preserving KOF as the seeded first tenant.
- Production guidance now describes Roadshow session-cookie authentication with optional API-token edge protection, replacing the older Basic Auth-only wording.

### Fixed

- Draft-slot selection is locked to `OpportunityWorkbench.best_window_for_cluster()`, and the regression test `test_draft_uses_same_best_slot_as_opportunity_workbench` asserts that the draft candidate slot matches the workbench best slot.

### Known Limitations

- Billing, email verification, payments, contracts, live travel booking, and full tenant-admin role management remain future work.
- Anonymous cross-tenant matching is deterministic and review-gated; it is not a live negotiation, chat, payment, or contract system.
- Live rail pricing still depends on authorized provider credentials; conservative first-class/full-fare estimates are used when live fare APIs are unavailable.
