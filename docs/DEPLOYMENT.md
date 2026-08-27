# Deployment target: Google Cloud

This is the intended production architecture — not yet provisioned. Nothing
here has been applied to a real GCP project; it's the plan to review before
anyone runs `gcloud` or `terraform apply` against real infrastructure.

## Why these services

The whole system already runs as two Docker images (`backend/Dockerfile`,
`frontend/Dockerfile`) plus Postgres, which maps directly onto Cloud Run +
Cloud SQL — no rearchitecting needed to deploy what's in this repo today.

| Component | Local (docker-compose) | GCP |
|---|---|---|
| Backend API | `backend` container, port 8080 | **Cloud Run** service |
| Frontend | `frontend` (nginx) container | **Firebase Hosting** or Cloud Run |
| Database | `db` (Postgres container) | **Cloud SQL for PostgreSQL** |
| Form images | local volume (`instance/uploads`) | **Cloud Storage** bucket |
| Secrets | `.env` file | **Secret Manager** |
| Container images | local Docker | **Artifact Registry** |
| CI/CD | — | **Cloud Build** (or GitHub Actions → `gcloud run deploy`) |

## Backend — Cloud Run

```bash
gcloud artifacts repositories create tally333 --repository-format=docker --location=us-central1

gcloud builds submit ./backend --tag us-central1-docker.pkg.dev/PROJECT_ID/tally333/backend

gcloud run deploy tally333-backend \
  --image us-central1-docker.pkg.dev/PROJECT_ID/tally333/backend \
  --region us-central1 \
  --add-cloudsql-instances PROJECT_ID:us-central1:tally333-db \
  --set-secrets DATABASE_URL=tally333-db-url:latest,JWT_SECRET_KEY=tally333-jwt:latest,SECRET_KEY=tally333-secret:latest,ANTHROPIC_API_KEY=tally333-anthropic-key:latest \
  --set-env-vars CORS_ORIGINS=https://<frontend-domain>,CV_BACKEND=claude \
  --min-instances 1 \
  --allow-unauthenticated
```

**`CV_BACKEND=claude` means every form upload is a billed Anthropic API
call** (`app/services/claude_vision.py`, `claude-opus-5`) — there's no local
fallback if the API is unreachable on election day. `CV_BACKEND=mock` is
only for local dev/tests, never for a real deployment.

**`--min-instances 1` matters here, not just for cold-start latency.**
Flask-SocketIO's default pub/sub is in-process — if Cloud Run scales the
backend to more than one instance, an agent's submission on instance A won't
push a `tally_updated` event to a dashboard connected to instance B. Two
ways to handle it as Election Day traffic grows:

1. Keep `--max-instances 1` for the backend (fine for this system's actual
   scale — bursts of station uploads, not consumer-app traffic) and rely on
   Cloud Run's per-instance concurrency instead of horizontal scaling.
2. Add a **Memorystore (Redis)** instance and set
   `SocketIO(message_queue="redis://...")` in `app/extensions.py` so
   multiple backend instances share pub/sub — needed if load testing (Section
   10 of the spec) shows one instance can't keep up.

Start with (1); it's simpler and matches the actual load shape (333 stations,
not 333,000 users).

## Database — Cloud SQL

```bash
gcloud sql instances create tally333-db --database-version=POSTGRES_16 --tier=db-g1-small --region=us-central1
gcloud sql databases create tally333 --instance=tally333-db
```

Connect from Cloud Run via the Cloud SQL Auth Proxy sidecar (the
`--add-cloudsql-instances` flag above wires this up automatically) using a
Unix socket `DATABASE_URL`:

```
postgresql+psycopg2://tally333:PASSWORD@/tally333?host=/cloudsql/PROJECT_ID:us-central1:tally333-db
```

Run `flask --app wsgi db upgrade` as a one-off Cloud Run job (or via
`gcloud sql connect` + local `flask db upgrade` against the proxy) after each
deploy that changes the schema.

## Form images — Cloud Storage

`backend/app/services/storage.py` is the swap point: implement a
`GCSStorage` class with the same `save(file_storage) -> (path, sha256)`
interface, writing to a bucket instead of local disk. Two follow-on changes:

- `FormSubmission.image_path` becomes a GCS object name instead of a
  filesystem path.
- `GET /api/submissions/:id/image` (`app/api/submissions.py`) swaps
  `send_file` for either a redirect to a **signed URL** (short-lived,
  matches the spec's "signed, time-limited URLs" requirement) or streaming
  the blob through Flask if you want to keep all image access behind the
  existing RBAC check.

## Frontend — Firebase Hosting (recommended) or Cloud Run

Firebase Hosting is a better fit than another Cloud Run service for a static
SPA build: free CDN, no cold starts, simpler custom-domain setup.

```bash
cd frontend
npm run build
firebase init hosting   # public directory: dist, single-page app: yes
firebase deploy --only hosting
```

Set `VITE_API_URL` to the deployed Cloud Run backend URL at build time
(it's baked into the JS bundle — see the gotcha below).

If you'd rather keep everything on Cloud Run (one platform, one billing
surface), `frontend/Dockerfile` already builds and serves via nginx — deploy
it the same way as the backend, just without `--add-cloudsql-instances`.

## Gotcha: `VITE_API_URL` is baked in at build time

Vite replaces `import.meta.env.VITE_API_URL` with a literal string during
`npm run build` — it is **not** read at runtime. If the backend URL changes
(new environment, new custom domain), the frontend must be rebuilt, not just
redeployed with a different env var. `docker-compose.yml`'s
`frontend.build.args.VITE_API_URL` shows the same thing locally: changing it
requires `docker compose build frontend` again, not just `up`.

## Secrets

```bash
echo -n "postgresql+psycopg2://..." | gcloud secrets create tally333-db-url --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create tally333-jwt --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create tally333-secret --data-file=-
echo -n "sk-ant-..." | gcloud secrets create tally333-anthropic-key --data-file=-
```

Never commit `backend/.env` — `.gitignore` already excludes it.

## Not yet covered here

- OTP delivery is real (SMTP, `app/services/email.py`) but untested at
  election-day volume — a real SMS channel (e.g. Africa's Talking) may be
  worth adding as a fallback if email deliverability becomes an issue.
- Candidate name matching is exact-normalized only (`app/services/candidates.py`)
  — no fuzzy matching. If Claude Vision reads the same candidate's name
  inconsistently across forms, they'll show up as separate candidates. Worth
  monitoring once real data starts flowing; not solved preemptively.
- CDN/WAF in front of the backend (Cloud Armor, if public-facing).
- The IEBC portal comparison job (Section 08 of the original spec) — not
  implemented; would run as a Cloud Scheduler + Cloud Run job once there's a
  source to pull official results from.
- `iebc_code` is null for all but Nyamira's ~332 imported polling stations —
  the national dataset (`backend/seed_data/kenya_geography.json`) has no
  official codes, only names. Fine for display/selection; don't build
  anything that assumes it's always present.
