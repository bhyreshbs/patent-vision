# PatentVision AI

Turns photographs of physical products into clean black-and-white, patent-style outline drawings.
Implements the prototype described in `PatentVision_AI_PRD.pdf`.

```
backend/    FastAPI + SQLAlchemy + Alembic + OpenCV pipeline (Python)
frontend/   Next.js + React + TypeScript + Tailwind dashboard
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
copy .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Register an account, create a project, upload a product photo, choose its view, press **Generate drawing**.
The image page shows the original, background-removed image, segmentation mask, extracted outline and the final
drawing side by side, with downloads for each.

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

`Uploaded → Queued → Processing → Completed | Failed`. A job only becomes `Completed` after all four output files
are written and verified. Any failure is stored (stage + message) on the job and result, partial outputs are
removed, and the job can be retried (`retry_count`). Jobs left `Queued`/`Processing` by a server restart are
surfaced as `Failed (interrupted)` on startup.

### API

All routes except `/auth/*` and `/health` require `Authorization: Bearer <token>`. Other users' resources return 404.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` · GET `/auth/me` | Accounts (scrypt password hashing, JWT) |
| POST/GET | `/projects` | Create / list |
| GET/PUT/DELETE | `/projects/{id}` | Details / update / delete (cascades rows and files) |
| POST/GET | `/projects/{id}/images` | Upload (multipart `file`, `view_type`) / list |
| GET/PATCH/DELETE | `/images/{id}` | Metadata / correct view / delete · `GET /images/{id}/original` |
| POST | `/ai/process/{image_id}` | Queue one image (409 if already active) |
| POST | `/ai/process/project/{project_id}` | Queue every non-active image in a project |
| GET | `/ai/results/{result_id}` | Result metadata and asset URLs |
| GET | `/ai/results/{result_id}/download?kind=drawing\|mask\|outline\|background_removed\|original` | Owner-only file download (`&download=true` for attachment) |
| GET | `/dashboard` | Counts, recent projects and results |

Errors are structured: `{"error": {"code", "message", "next_action"?}}`. Responses never contain filesystem paths;
the database stores keys relative to `PV_STORAGE_ROOT`.

### Configuration

All settings use the `PV_` prefix (see `backend/.env.example`): database URL, storage root, secret key, upload
size limit, processing resolution, segmenter, rate limit, concurrent-job limit, CORS origins.

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

## Deployment

- **Frontend → Vercel.** Import the repo, set **Root Directory** to `frontend`, and add the environment variable
  `NEXT_PUBLIC_API_URL` = the public URL of the backend (no trailing slash).
- **Backend → any Docker host with a persistent disk** (`render.yaml` is a ready Render blueprint; `backend/Dockerfile`
  works anywhere). The backend keeps SQLite and all images on disk and runs jobs in-process, so it cannot run on
  Vercel Functions (read-only, ephemeral filesystem). Set `PV_CORS_ORIGINS=["https://<your-vercel-domain>"]`, a long
  random `PV_SECRET_KEY`, and mount the disk at `/data` (`PV_DATABASE_URL=sqlite:////data/patentvision.db`,
  `PV_STORAGE_ROOT=/data/storage`). Run a single instance.

## Scope notes

- Implemented: FR-01 through FR-11 and FR-13 (separate drawing per view; failed views reprocess individually).
- Not implemented (PRD marks post-MVP/later): FR-12 manual editor, FR-14 SVG/PDF patent-sheet export, HEIC decoding
  (rejected with a clear message), object storage, subscriptions.
- Thresholds in `mask_validation.py` and `background.py` are tuned on synthetic photos with exact ground truth;
  validate them against a representative real-photo set before relying on the success-metric targets in PRD §16.
- Rate limiting and job execution are in-process (single-server prototype). Use a real queue and shared limiter
  store for multi-worker deployments.
