# Tally333

A parallel vote tabulation (PVT) system for Kenyan elections — field agents
photograph a results form at their polling station, Claude Vision reads the
candidate names and vote counts off it, and a live dashboard tallies results
in real time as submissions are approved. Covers all 6 elective positions
(President, Governor, Senator, Woman Representative, MP, MCA) across the
real national geography (47 counties, 290 constituencies, ~1,450 wards,
~24.6k polling stations).

This repo has two parts:

- **CV research/training** (repo root) — `iebc_scrap.py`, `pdf_to_images.py`,
  `auto_label.py`, `train_form34a.py`, `dataset/`, `runs/`: an earlier,
  abandoned attempt at a trained YOLOv8 field-level detector (single-class,
  whole-page only — never reached per-field extraction). The application no
  longer depends on this; see "Extraction" below.
- **The application** — `backend/` (Flask API) and `frontend/` (React +
  Vite + shadcn/ui), described below.

## Roles

- **Agent** — signs up (phone/email/OTP), then photographs/uploads their
  assigned form. Never picks their own station or position.
- **Campaign manager** — onboards agents: assigns each one to a specific
  county → constituency → ward → polling station *and* the elective position
  they're tracking (`/campaign-manager`).
- **Coordinator/admin** — moderates flagged submissions: corrects misread
  fields, approves/rejects/flags duplicates (`/admin`).
- **Viewer** — read-only dashboard access.

## Quickstart (Docker)

```bash
cp backend/.env.example backend/.env   # set ANTHROPIC_API_KEY for real extraction (see below)
docker compose up -d --build
docker compose exec backend flask --app wsgi db upgrade
docker compose exec backend flask --app wsgi import-geography   # national county/constituency/ward/station data + the 6 positions
docker compose exec backend flask --app wsgi seed               # demo accounts only — no fake candidates/submissions
```

- Dashboard: http://localhost:5173
- API: http://localhost:8000/api/health

Demo accounts (from `seed.py`) — all sign in via `/login` with a one-time
code, no password:

| Role | Phone | Code delivered to |
|---|---|---|
| Admin | `+254700000001` | `admin@example.com` |
| Coordinator | `+254700000002` | `coordinator@example.com` |
| Campaign manager | `+254700000003` | the fixed campaign-manager inbox |
| Agent | `+254711111111` | `demo.agent@example.com` (no station/position assigned yet) |

## Quickstart (local dev, no Docker)

Backend needs a Postgres instance — either `docker compose up -d db` or your
own, with `DATABASE_URL` in `backend/.env` pointed at it.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # edit DATABASE_URL if not using docker compose's db
flask --app wsgi db upgrade
flask --app wsgi import-geography
flask --app wsgi seed
python wsgi.py          # http://localhost:5000
```

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_URL should match the backend above
npm run dev              # http://localhost:5173
```

Run the backend test suite with `pytest` (needs `TEST_DATABASE_URL` — see
`backend/app/config.py`). Tests always use the mock extraction backend
regardless of `CV_BACKEND` in `.env`, so running them never calls the real
Claude API.

## Architecture

```
Agent (React)  →  Flask API  →  Claude Vision extraction (app/services/claude_vision.py)
                       ↓
                 PostgreSQL (geography, positions, dynamic candidates, submissions, votes)
                       ↓
           Socket.IO "tally_updated"  →  Live dashboard (React), scoped by position + geography
```

- **Geography**: County → Constituency → Ward → PollingStation, imported
  once from a static national dataset (`flask import-geography` — see
  `backend/import_geography.py`). Cascading selects fetch each level lazily
  (`GET /api/geography/{counties,constituencies,wards,stations}`) rather than
  loading the whole tree, since it's ~24.6k stations.
- **Elective positions**: 6 static rows (`ElectivePosition`), each with a
  `level` (national/county/constituency/ward) that determines both the
  geographic scope of its candidates and the real IEBC form series
  (34=President, 35=MP, 36=MCA, 37=Governor, 38=Senator, 39=Woman Rep).
- **Candidates are dynamic**: nobody pre-seeds a candidate list. The first
  time a name is read off a form for a given position+geography, a
  `Candidate` row is created (`app/services/candidates.py`). No fuzzy name
  matching yet — see the code comment there for the known limitation.
- **Auth**: every role signs in via phone/OTP — a one-time code emailed to
  the account's address on file (see `app/services/email.py`), except
  campaign managers, whose code always goes to a fixed inbox regardless of
  who's signing in (see `CAMPAIGN_MANAGER_OTP_EMAIL` in `app/api/auth.py`).
  No passwords anywhere. JWT-based, role claims enforced with
  `app/utils/rbac.py`.
- **Assignment**: `PATCH /api/agents/:id/assignment` (campaign_manager/admin
  only) sets an agent's station and position — never self-service.
- **Upload flow**: `POST /api/submissions/draft` (image + station) runs
  extraction against the *agent's assigned position* and returns a preview
  without touching the tally; `POST /api/submissions/:id/finalize` applies
  dedup/arithmetic/confidence gates and either auto-approves or routes to
  `pending_review`.
- **Review flow**: `POST /api/submissions/:id/review` lets a
  coordinator/admin correct misread fields and approve/reject/flag-duplicate;
  every action is written to `verification_log`.
- **Tally**: computed live per position (+ geographic scope for
  county/constituency/ward-level positions) from approved station-level
  submissions only — see `app/services/tally_service.py`. Analytics start
  genuinely blank; a race only appears once a real submission has been
  extracted for it.

## Extraction: Claude Vision

`backend/app/services/cv_pipeline.py` defines the `ExtractionService`
interface. Two implementations:

- `MockExtractionService` — deterministic fake data, no API key needed. Used
  by tests and whenever `CV_BACKEND=mock`.
- `ClaudeExtractionService` (`app/services/claude_vision.py`) — the real
  backend. Sends the form image to `claude-opus-5` with a forced tool call
  for reliable structured output (candidate names, votes, totals, rejected
  ballots, legibility). Requires `ANTHROPIC_API_KEY` and `CV_BACKEND=claude`
  in `backend/.env`. **Every upload is a billed API call** — there's no
  offline fallback for a real deployment if Anthropic's API is unreachable.

PDF uploads (scanned forms) are converted to an image server-side first
(`app/services/pdf.py`, first page only) — same extraction path either way.

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the target GCP
architecture (Cloud Run, Cloud SQL, Cloud Storage, Secret Manager).
