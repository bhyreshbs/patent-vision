# PatentVision AI

Turns photographs of physical products into clean black-and-white, patent-style outline drawings.
Implements the prototype described in `PatentVision_AI_PRD.pdf`.

```
backend/    FastAPI + SQLAlchemy + Alembic + OpenCV pipeline (Python)  → served at /api
frontend/   Next.js + React + TypeScript + Tailwind dashboard          → served at /
vercel.json Vercel Services: both deploy together as one project on one domain
```

> Drawings are drafts that assist patent preparation. They do not guarantee patent-office acceptance and should
> be reviewed by a patent professional.

## Quick start

### Backend (http://localhost:8000, docs at `/docs`)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt   # requirements.txt alone is enough to run (no test tools)
copy .env.example .env          # set PV_SECRET_KEY to a long random value
alembic upgrade head            # create the schema (dev also auto-creates tables on startup)
uvicorn app.main:app --reload
```

### Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev                     # proxies /api/* to http://127.0.0.1:8000 (override with API_PROXY_TARGET)
```

Register, create a project and drop product photos onto it. With **Generate drawings automatically** on, each
photo is processed right after upload. The image page shows a pipeline stepper (which stage passed or failed),
a before/after slider comparing the photo with the outline, mask or cut-out, the final drawing, processing details
and downloads (drawing as PNG and SVG, mask, outline, cut-out, original).

### See the pipeline without the web app

```bash
cd backend
python scripts/demo.py          # writes ../samples/<case>/*.png and ../samples/contact_sheet.png
```

## Tests

```bash
cd backend  && pytest                 # unit, API/integration, visual-regression, migration tests
cd frontend && npm test && npm run typecheck && npm run build
```

## How it works

`load → background removal → product localization → segmentation → mask validation → contour extraction/smoothing
→ drawing rendering → output validation → persistence` (`backend/app/ai/pipeline.py`). Every stage validates its
input and output and raises a `PipelineError` naming the failed stage plus a next action.

| Stage | Module | Notes |
|---|---|---|
| Background removal | `ai/background.py` | Border-colour model in Lab + Otsu; soft shadows are down-weighted. Transparent PNGs use their alpha. |
| Localization | `ai/localization.py` | Foreground-mask localization: merges nearby parts (feet, dividers, holders), drops far-away blobs, validates/clips the box. |
| Segmentation | `ai/segmentation.py` | `classical` (GrabCut refinement, no model files) or `sam` (Segment Anything, needs checkpoint). Swappable via `PV_SEGMENTER`. |
| Mask validation | `ai/mask_validation.py` | Rejects empty, tiny, whole-image, border-hugging, **incomplete** (e.g. one compartment of an organizer) or contaminated masks. Candidates are tried in order; the chosen one and every rejection reason are stored in `metrics`. |
| Contour | `ai/contour.py` | External contour(s), speck removal, corner-preserving smoothing. Default is strict outer outline (PRD FR-09). `PV_KEEP_OPENINGS=true` also keeps large see-through openings (mug handles) as inner contours, but a light label on a light background can then be mistaken for an opening. |
| Rendering | `ai/rendering.py` | White canvas, uniform anti-aliased black line (4× supersampled), margins, whole object visible. Output is validated (white background, margins, stroke uniformity) before a job can complete. |

### Statuses and failures

`Uploaded → Queued → Processing → Completed | Failed`. Processing runs inside the request that starts it (about a
second per photo), and claiming a job is atomic, so the same image can never be processed twice at once. A job only
becomes `Completed` after every output file is written and verified. Any failure is stored (stage + message) on the
job and result, partial outputs are removed, and the job can be retried (`retry_count`). A job still in flight after
`PV_STALE_JOB_MINUTES` (default 10) lost its worker and is shown as `Failed (interrupted)`.

### API

All routes except `/auth/*`, `/meta` and `/health` require `Authorization: Bearer <token>`. Other users' resources
return 404. Routes answer both at `/…` (local) and `/api/…` (as routed on Vercel).

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` · GET `/auth/me` | Accounts (scrypt password hashing, JWT) |
| POST/GET | `/projects` | Create / list |
| GET/PUT/DELETE | `/projects/{id}` | Details / update / delete (cascades rows and files) |
| POST/GET | `/projects/{id}/images` | Upload (multipart `file`, `view_type`) / list |
| GET/PATCH/DELETE | `/images/{id}` | Metadata / correct view / delete · `GET /images/{id}/original` |
| POST | `/ai/process/{image_id}` | Process one image; returns its final status (409 if already in flight) |
| POST | `/ai/process/project/{project_id}` | Process every image in a project that is not in flight |
| GET | `/ai/results/{result_id}` | Result metadata and asset URLs |
| GET | `/ai/results/{result_id}/download?kind=drawing\|svg\|mask\|outline\|background_removed\|original` | Owner-only file download (`&download=true` for attachment) |
| GET | `/dashboard` · `/meta` | Counts, recent projects and results · public upload limits |

Errors are structured: `{"error": {"code", "message", "next_action"?}}`. Responses never contain filesystem paths
or storage URLs; files are always served through the API after an ownership check.

### Configuration

All settings use the `PV_` prefix (see `backend/.env.example`): database URL (falls back to `DATABASE_URL` /
`POSTGRES_URL`), storage backend (`local` / `blob` / `auto`), secret key, upload size limit, processing resolution,
segmenter, rate limit, concurrent-job limit, stale-job timeout, CORS origins.

## Using Segment Anything instead of the classical segmenter

```bash
pip install torch segment-anything
# download a checkpoint (e.g. sam_vit_b_01ec64.pth) into backend/checkpoints/
set PV_SEGMENTER=sam
set PV_SAM_CHECKPOINT=checkpoints/sam_vit_b_01ec64.pth
```

SAM is prompted with the localized product box. If a checkpoint or the package is missing the job fails with a
clear `segmentation` error instead of silently degrading. Its candidate masks go through the same validation, and
the foreground mask is the controlled fallback when SAM returns an incomplete mask. This path is not exercised by
the automated tests (no model files in CI).

## Deployment (Vercel)

One Vercel project, configured by `vercel.json` with **Vercel Services**: the Next.js app serves `/`, the FastAPI
app serves `/api/*`, and both ship in the same deployment on one domain (no CORS).

| Need | On Vercel | Setting |
|---|---|---|
| Database | Neon Postgres (Marketplace) | `DATABASE_URL` is injected when the store is connected to the project |
| Files (uploads, outputs) | Vercel Blob, **private** store | `BLOB_READ_WRITE_TOKEN` is injected when the store is connected |
| Login token signing | Project environment variable | `PV_SECRET_KEY` (long random value, type *sensitive*) |

Project settings: Framework Preset **Services**, Root Directory empty (repo root). Every push to `main` deploys.
Tables are created automatically on first request (`PV_AUTO_CREATE_TABLES=true`); to manage the schema with Alembic
instead, run `alembic stamp head` once against the database and `alembic upgrade head` on later changes.
Without a database the API answers `503 database_not_configured` instead of silently using temporary storage.

Serverless limits that shaped the design: request bodies are capped at 4.5 MB, so uploads are limited to 4 MB and
the web app re-encodes larger photos in the browser; files are always read through the API (private Blob store);
jobs finish inside the request.

`backend/Dockerfile` and `render.yaml` remain for hosting the API on a container platform with a persistent disk
instead (`PV_DATABASE_URL=sqlite:////data/patentvision.db`, `PV_STORAGE_ROOT=/data/storage`).

## Scope notes

- Implemented: FR-01 through FR-11, FR-13 (separate drawing per view; failed views reprocess individually), and from
  later scope: before/after comparison and SVG export of the drawing.
- Not implemented (PRD marks post-MVP/later): FR-12 manual editor, drawing sheets/figure numbering/PDF export, HEIC
  decoding (rejected with a clear message), subscriptions.
- Thresholds in `mask_validation.py` and `background.py` are tuned on synthetic photos with exact ground truth;
  validate them against a representative real-photo set before relying on the success-metric targets in PRD §16.
- The rate limiter is per process (on serverless, per instance). Use a shared store such as Upstash Redis for a
  strict global limit.
