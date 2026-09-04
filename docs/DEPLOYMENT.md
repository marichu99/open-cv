# Deployment target: Google Cloud

This is the intended production architecture. Most of it is still just the
plan to review before running `gcloud`/`terraform apply` — but as of
2026-08-31, project `project-x-477317` (us-central1) has two pieces of the
50,000-user scaling plan actually provisioned:

- **Memorystore Redis** `tally333-redis` — Basic tier, 1GB,
  `10.237.108.179:6379` (VPC-internal, `default` network).
- **Serverless VPC Access connector** `tally333-connector` — `10.8.0.0/28`,
  `default` network, `us-central1` — lets Cloud Run services reach the Redis
  instance above via `--vpc-connector=tally333-connector`.
- **Cloud SQL for PostgreSQL** `tally333-db` — `db-g1-small`, Enterprise
  edition, **Regional (HA)** availability, `us-central1`. Connection name
  `project-x-477317:us-central1:tally333-db`, database `tally333`, app user
  `tally333`. The connection string is in **Secret Manager** as
  `tally333-db-url` (Unix-socket form, matching the "Database — Cloud SQL"
  section below) — the password was generated at creation time and was never
  printed or stored anywhere else. Schema migrations have been applied
  (`flask db upgrade`, run via a one-off Cloud Run job, `tally333-db-migrate`).
  National geography and elective positions are seeded too (47 counties,
  290 constituencies, ~1,450 wards, ~24.6k polling stations, all 6
  positions) — `flask --app wsgi import-geography`, run the same way via a
  one-off job, `tally333-geo-import` (see "Populating geography data"
  below). No agent/candidate/vote data — that only exists from real usage.
- **Artifact Registry** `tally333` (docker, `us-central1`) — holds the
  backend image, `us-central1-docker.pkg.dev/project-x-477317/tally333/backend`.
- **Cloud Run** `tally333-api` and `tally333-realtime` — both deployed from
  that image, both currently `--min-instances 1` (`tally333-realtime` also
  `--max-instances 1`, since Redis fan-out is wired but this hasn't been
  load-tested yet — see "Sizing and rollout" above before raising it).
  `tally333-api` has `CV_BACKEND=claude` and `ANTHROPIC_API_KEY` (Secret
  Manager, `tally333-anthropic-key`) — **every form upload is now a real,
  billed `claude-opus-5` call**, switched on deliberately after the mock
  backend's placeholder numbers were mistaken for a real extraction bug.
  `tally333-realtime` is still `CV_BACKEND=mock` — harmless, since it never
  serves `/api/submissions/*` (same reasoning as the SMTP/GCS config, only
  `tally333-api` needs upload-path env vars), but worth knowing so the two
  services' env vars aren't assumed to be identical. `tally333-api` also
  runs at `--memory=2Gi` (not the 512Mi default) after a real upload
  OOM-killed the instance mid-request — see the memory gotcha below. URLs:
  - `tally333-api`: https://tally333-api-82161509094.us-central1.run.app
  - `tally333-realtime`: https://tally333-realtime-82161509094.us-central1.run.app
- `tally333-jwt`, `tally333-secret`, `tally333-anthropic-key` — all
  generated/stored in Secret Manager.
- **Firebase Hosting** — live at https://project-x-477317.web.app, built
  with `VITE_SOCKET_URL` pointed directly at `tally333-realtime` (no LB in
  front of long-lived Socket.IO connections) and `VITE_API_URL` pointed at
  the load balancer, `https://8-232-246-179.nip.io`, **not**
  `tally333-api` directly — that's what actually puts Cloud CDN caching and
  the Cloud Armor rate limit in the real request path (see the
  `VITE_API_URL` gotcha below — a backend URL change needs a frontend
  rebuild + redeploy, not just a Cloud Run update). Both Cloud Run
  services' `CORS_ORIGINS` include this origin — verified with an actual
  CORS preflight through the LB, not just assumed.
- **SMTP (OTP email delivery)** — `tally333-api` has `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `EMAIL_FROM` set and `SMTP_PASSWORD` in Secret
  Manager as `tally333-smtp-password` (the Gmail app password from
  `backend/.env`, moved there rather than left as a plain env var). Also set
  `FLASK_ENV=production`, so a future SMTP failure raises instead of being
  silently swallowed (`services/email.py`'s dev-only catch). Verified with a
  real OTP send that arrived. **Not set on `tally333-realtime`** — the
  frontend only sends REST/auth traffic to `tally333-api`
  (`VITE_API_URL`), so the realtime service never serves `/api/auth/*`.
- **Cloud Storage for form images** — bucket
  `project-x-477317-tally333-forms` (`us-central1`, uniform bucket-level
  access). `tally333-api` has `STORAGE_BACKEND=gcs` and `GCS_BUCKET_NAME`
  set; the Cloud Run service account has `roles/storage.objectAdmin`
  scoped to just this bucket. See "Form images — Cloud Storage" below for
  the code-level design (why processing still happens on local disk, only
  persistence moved to GCS) — verified end-to-end with a real
  upload/download roundtrip run as the actual service account (Cloud Run
  job `tally333-gcs-check`), not just tested locally.
- **External HTTPS Load Balancer + Cloud CDN + Cloud Armor** in front of
  `tally333-api` — static IP `8.232.246.179`
  (`tally333-lb-ip`), serving on `https://8-232-246-179.nip.io` (a nip.io
  domain, not a branded one — no custom domain owned yet; see "CDN and
  Cloud Armor" below for how to swap one in later). Chain: forwarding rule
  → target HTTPS proxy (`tally333-api-cert`, Google-managed) → URL map →
  backend service `tally333-api-backend` (Cloud CDN enabled, Cloud Armor
  policy `tally333-armor-policy` attached — 100 req/min per-IP rate limit,
  `deny(429)` over threshold) → serverless NEG `tally333-api-neg` →
  `tally333-api`. The managed SSL cert reached `ACTIVE` and the full chain
  is verified working — `curl https://8-232-246-179.nip.io/api/health`
  returns `200` from `tally333-api` over HTTPS through the LB. **The
  frontend now actually routes through it** (`VITE_API_URL`, above), and
  **Cloud CDN is genuinely caching, not just proxying** — geography/
  positions/tally read endpoints carry real `Cache-Control` headers now
  (`app/utils/caching.py`, see "CDN and Cloud Armor" below), confirmed by
  a repeated request's `Age` header actually incrementing (`9` → `11`
  across two requests a second apart) rather than staying `0`.
- **Async form extraction** — fully live (see "Async form extraction"
  below). `tally333-extraction-worker` (`--no-allow-unauthenticated`,
  `--memory=2Gi`, `--concurrency=1`, `--min-instances=0`,
  `--max-instances=5`): https://tally333-extraction-worker-82161509094.us-central1.run.app.
  Cloud Tasks queue `tally333-extraction-queue` (`us-central1`,
  `--max-concurrent-dispatches=5`, `--max-dispatches-per-second=5` — a
  conservative placeholder, not sized against a real Anthropic rate limit;
  see "Async form extraction" for how to raise it). Service account
  `tally333-tasks-invoker@project-x-477317.iam.gserviceaccount.com` holds
  `roles/run.invoker` on the worker, and `tally333-api`'s own runtime SA
  holds `roles/iam.serviceAccountUser` on it (needed to mint OIDC tokens on
  its behalf when creating tasks). `tally333-api` has `GCP_PROJECT`,
  `CLOUD_TASKS_LOCATION`, `CLOUD_TASKS_QUEUE`, `EXTRACTION_WORKER_URL`, and
  `TASKS_INVOKER_SERVICE_ACCOUNT` set, so it now genuinely dispatches Cloud
  Tasks instead of the local inline fallback. **Verified with a real
  upload against the live deployment**: `202`/`"processing"` immediately,
  resolved to `"draft"` ~16-20s later after the real
  Cloud Tasks → OIDC-authenticated call → `tally333-extraction-worker` →
  real Claude Vision round trip — confirmed in the worker's own logs, not
  just inferred from the final state.

Not provisioned yet: a real domain for the load balancer (nip.io is a
placeholder) and `tally333-extraction-queue`'s concurrency being sized
against a real Anthropic rate limit rather than the conservative
placeholder of 5.

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

**This single-service command is superseded** — `project-x-477317` deployed
the two-service split from "Scaling to 50,000 concurrent users" below
(`tally333-api` + `tally333-realtime`) from day one rather than this
baseline `tally333-backend`. Two gotchas hit while running the real
deploy, worth knowing before running any variant of this command:

- **`--set-secrets ...` fails with a permission error** the first time,
  even with correct secret names — Cloud Run's default service account
  (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) needs the
  `roles/secretmanager.secretAccessor` role granted explicitly:
  `gcloud projects add-iam-policy-binding PROJECT_ID --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"`.
  One-time setup, not needed again per-deploy.
- **`--set-env-vars` uses `,` as its own key=value delimiter**, so a value
  that itself contains a comma (like a multi-origin `CORS_ORIGINS`) breaks
  the parser. Use gcloud's alternate-delimiter syntax instead:
  `--set-env-vars "^@^KEY1=val1@KEY2=val,with,commas"`.
- **This command has no `--memory` flag, which means Cloud Run's 512Mi
  default** — too little for `tally333-api` specifically. A real upload
  does PDF→image conversion (PyMuPDF), Pillow decoding, and base64-encodes
  the image for the Claude Vision call, all within one request; on
  `project-x-477317` this OOM-killed the instance mid-request
  (`Memory limit of 512 MiB exceeded with 525 MiB used`, from
  `gcloud logging read`) — the connection resets with no HTTP response, so
  the frontend just shows a generic "Network Error" with no useful detail.
  Add `--memory=2Gi` for `tally333-api`. `tally333-realtime` never touches
  image processing, so its default is fine as-is.

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

## Scaling to 50,000 concurrent users

The plan above assumes the actual load shape of this system: 333 agents
uploading forms. If the public-facing side needs to support 50,000
concurrent users — most reading published results, a smaller subset watching
the dashboard live via Socket.IO — several pieces above need to change
before that traffic arrives, not after. This section supersedes the
`--min-instances`/`--max-instances 1` guidance and the "start with (1)"
recommendation above; nothing here is applied yet either.

### Split into two Cloud Run services from the same image

Today one Flask app (`create_app()` in `backend/app/__init__.py`) serves both
REST blueprints and Socket.IO from a single `gunicorn --worker-class
eventlet -w 1` process. At this scale, split by traffic shape instead of
scaling that one process wider:

| Service | Serves | Worker model | Scales by |
|---|---|---|---|
| `tally333-api` | REST blueprints (`/api/...` reads/writes) | sync gunicorn workers, no eventlet | request volume / CPU |
| `tally333-realtime` | Socket.IO only (dashboard clients) | `eventlet`, current `wsgi.py` entrypoint | open connection count |

Both deploy from the same container image — `backend/docker-entrypoint.sh`
picks the gunicorn command based on a `SERVICE_ROLE` env var:
`SERVICE_ROLE=api` runs plain sync workers (`-w ${WEB_CONCURRENCY:-4}`, no
eventlet); anything else (including unset, which is what local
`docker-compose` uses) runs today's `eventlet -w 1` command unchanged. So
`tally333-api` deploys with `--set-env-vars SERVICE_ROLE=api,...` and
`tally333-realtime` deploys without it.

`review.py` and `submissions.py` call `socketio.emit("tally_updated", ...)`
directly inside REST handlers; with `message_queue` pointed at Redis
(below), that emit publishes from `tally333-api` instances and any
subscribed `tally333-realtime` instance delivers it to its connected
browsers — this is Flask-SocketIO's documented multi-process pattern, not a
custom mechanism. The frontend now has two base URLs — `VITE_API_URL` for
REST, `VITE_SOCKET_URL` for the Socket.IO connection (`frontend/src/lib/api.ts`,
`frontend/src/lib/socket.ts`) — so it can point each at its own Cloud Run
service; `VITE_SOCKET_URL` defaults to `VITE_API_URL` when unset, which is
why local `docker-compose` (one combined backend container) doesn't need to
set it separately.

### Redis (Memorystore) for Socket.IO fan-out is no longer optional

`app/config.py`'s `REDIS_URL` (read by `app/__init__.py` via
`socketio.init_app(app, message_queue=app.config["REDIS_URL"])`) is `None`
by default — fine for a single instance, broken the moment
`tally333-realtime` scales past one. At 333-station scale this was deferred
as a "revisit if load testing shows it's needed" item; at 50,000 it's a
day-one requirement. **Memorystore for Redis is already provisioned**
(`tally333-redis`, Basic tier, 1GB, `us-central1-a`) — set
`REDIS_URL=redis://10.237.108.179:6379/0` on **both** Cloud Run services
(the API service publishes, the realtime service subscribes) so a
submission event reaches every connected viewer regardless of which
`tally333-realtime` instance holds their socket.

Memorystore is VPC-internal only — both services need the already-created
**Serverless VPC Access connector** `tally333-connector`
(`10.8.0.0/28`, `default` network, `us-central1`) to reach it:
`--vpc-connector=tally333-connector`, the same way
`--add-cloudsql-instances` is already needed for Cloud SQL above.

### Fixed: coordinator moderation queue didn't live-refresh

Reported as "the agent upload does not refresh the feed, it requires a hard
refresh." Diagnosed by proving each hop of the pipeline independently
against the real deployment, in order, rather than guessing:

1. A one-off Cloud Run Job (Python, `redis-py`) subscribed directly to
   Redis pub/sub (`psubscribe('*')`) while a real `finalize()` call was
   fired against `tally333-api` — confirmed the publish side works:
   `tally_updated` genuinely reaches Redis on the `flask-socketio` channel.
2. A real `socket.io-client` (Node.js) connected to `tally333-realtime` and,
   with a real `finalize()` fired mid-connection, received the relayed
   `tally_updated` event within ~1s — confirmed the relay side works too
   (an intermittent Engine.IO ping-timeout disconnect was observed and
   auto-recovered, not a bug — see below).
3. A headless-Chromium session (Playwright) against the actual
   `https://project-x-477317.web.app/dashboard`, with a real `finalize()`
   fired mid-session, showed the new station row appear with no reload —
   confirming `useLiveResource` (`frontend/src/lib/hooks.ts`) — the
   dashboard's socket-listener-plus-20s-poll hook — works end-to-end.

So the whole live-update mechanism was sound. The actual bug: `AdminPage.tsx`
(the coordinator's moderation/discrepancies queue) never used
`useLiveResource` at all — it fetched `/api/submissions` once on mount via
a bespoke `useCallback`, with no socket listener and no poll fallback. A
newly-flagged submission, or another reviewer resolving one (`review.py`'s
manual-approve/reject also emits `tally_updated`), simply never appeared
without a manual reload — the one page that was never wired into the
mechanism every other view already had. Fixed by adding
`useSubmissionsFeed()` to `hooks.ts`, a thin wrapper around the same
`useLiveResource` used everywhere else. Re-verified with the same
Playwright-plus-real-`finalize()` approach against the redeployed page: the
"N shown" count updated live, no reload, ~1.2s after `finalize()` returned.

**Gotcha hit repeatedly while building the diagnostic scripts**: passing a
multi-statement Python payload to a one-off Cloud Run Job via
`gcloud run jobs deploy --args="^;^-c;import x;exec(...)"` silently split
into *three* args on the semicolon inside the payload itself, not two —
`python3 -c "import x"` ran (doing nothing, exiting 0) while the actual
exec call sat inert in `sys.argv[2]`, never executed. No error, no
non-zero exit, just silent no-op success — worth remembering next to the
comma-delimiter gotcha above. Fixed by writing the payload as one
statement (`exec(__import__('base64').b64decode(...).decode())`) that
needs no semicolon at all, sidestepping the delimiter question entirely.
Also: Cloud Run Jobs' stdout capture into Cloud Logging proved unreliable
enough during this investigation that the more robust pattern was to have
the job write its findings straight to GCS (`google-cloud-storage`, same
credentials the job already had for Cloud SQL) and read them back with
`gcloud storage cat`, rather than trust `gcloud logging read`.

### Cache the read-only path at the edge

Most of the 50,000 users are reading, not holding a socket open. Put an
external **HTTPS Load Balancer + Cloud CDN** in front of `tally333-api`
(Cloud Run supports this as a serverless NEG backend) and set `Cache-Control`
on the read endpoints that can tolerate a few seconds of staleness (results,
stats, roster). This is the highest-leverage change here — it turns "50,000
requests" into "50,000 requests mostly served from cache," and is what keeps
Cloud SQL and the `tally333-api` instances from taking the full brunt.

### Database

`db-g1-small` (the tier in the command above) won't hold at this scale:

- Bump the Cloud SQL tier to match measured load (only load testing tells you
  the real number — don't guess a tier here).
- Add a **read replica** for `tally333-api`'s read traffic once the cache
  layer's miss rate is known.
- Put connection pooling in front of Postgres. Cloud Run's per-instance
  connection multiplication exhausts Postgres `max_connections` fast at this
  scale — either a PgBouncer sidecar, or evaluate **AlloyDB for PostgreSQL**,
  which has pooling built in and is otherwise drop-in compatible.

### Cloud Armor

A public, high-visibility, election-adjacent service at this traffic level is
a plausible DDoS/abuse target. Put **Cloud Armor** on the load balancer in
front of `tally333-api` (rate limiting at minimum) before go-live — this was
listed as a "not yet covered" nice-to-have above; at 50,000 concurrent it's a
prerequisite, not a nice-to-have.

### Sizing and rollout

- `min-instances` ≥ 2 on both services — a cold start during a traffic spike
  is worse at this scale than the idle cost of keeping warm instances.
- Concurrency and instance-count numbers for `tally333-realtime` depend on
  how many of the 50,000 are actually socket-connected (a subset, per the
  traffic shape above) — size it from that number, not from 50,000.
- Load test (k6 or Locust) both paths — REST read volume against the CDN/API
  tier, and simulated Socket.IO connections against the realtime tier —
  before go-live. Section 10 of the original spec deferred this at
  333-station scale; it can't be deferred at this one.

## Async form extraction (for very high concurrent *upload* volume)

**Implemented and provisioned** (see the intro), prompted by "what would
25,000 concurrent uploads need?" Everything above (CDN, Cloud Armor, the
API/realtime split) scales the *read* side — public viewers hitting the
dashboard. Uploads are a different traffic shape entirely: 333 polling-
station agents today, but the question of "what if it were 25,000
concurrent uploads" exposed a real architectural limit that no amount of
Cloud Run sizing would have fixed on its own.

### The actual bottleneck isn't Cloud Run

`create_draft()` (`app/api/submissions.py`) is synchronous end to end: a
gunicorn worker holds the HTTP connection open for the *entire* Claude
Vision call (`app/services/claude_vision.py`, several seconds per form)
before it can respond. Concurrent uploads == concurrent in-flight Claude
API calls == concurrent held-open workers, one-to-one. Two hard ceilings
follow from that, and only one of them is under this project's control:

1. **Anthropic's rate limit on this API key.** No standard tier sustains
   25,000 concurrent `claude-opus-5` vision calls — that needs an
   enterprise-negotiated quota, or spreading load across multiple keys.
   This number has to come from Anthropic directly; nothing below should
   be sized by guessing it.
2. **Memory/worker count**, which is what the 512Mi OOM-kill earlier in
   this session was already a small version of — more workers holding
   image buffers simultaneously needs proportionally more memory. This one
   *is* fixable with more Cloud Run capacity, but only up to whatever (1)
   actually allows through.

Point (1) means past a fairly low concurrency, more Cloud Run instances
stop helping — they'd just all be blocked on the same external rate limit,
holding memory and doing nothing. The fix is architectural, not "bigger
instance."

### The redesign: decouple accepting an upload from extracting it (implemented)

Split `create_draft()`'s one synchronous request into two phases connected
by a queue, so upload-accept throughput and Claude-call throughput scale
independently — and a surge past Anthropic's sustainable rate becomes
"agents wait longer for their preview," not dropped uploads or 429s.

**Phase 1 — stays on `tally333-api`, fast, unchanged in spirit:**
`create_draft()` keeps today's local-disk write, `looks_blank()` check, and
the dedup check exactly as they are now — all fast, all local. What
changes: instead of calling `service.extract()` inline, it uploads the
image to GCS immediately (moving that step earlier than today), creates
the `FormSubmission` row with a new `"processing"` status (add it to
`STATUSES` in `app/models/submission.py`, before `"draft"` — the row's
`vote_records`/`total_votes_cast`/`ocr_confidence_avg` stay empty until
phase 2 fills them in, which the schema already allows since those columns
are nullable), enqueues one Cloud Task carrying just the submission id, and
returns `202` immediately. No more holding a worker open on the Claude
call.

**Phase 2 — a new, deliberately rate-limited Cloud Run service,
`tally333-extraction-worker`:** same image, same code, `--no-allow-
unauthenticated` (never publicly reachable — only Cloud Tasks can call it,
via OIDC). A new internal route (e.g. `POST
/internal/submissions/<id>/extract`) does what `create_draft()` used to do
inline: download the image from GCS, run `looks_blank()`/`service.extract()`/
`location_mismatches()` exactly as today, and either:
- populate `vote_records`, `total_votes_cast`, etc. and set
  `status="draft"` (ready for the agent to review/confirm, same as today), or
- set a new terminal status `"extraction_failed"` (distinct from the
  existing `"rejected"`, which means a *human reviewer* rejected it — this
  means the pipeline itself couldn't process the photo, e.g. blank/
  mismatched-location, and the agent needs to retake) — deliberately not
  reusing `"rejected"`'s meaning.

Then emit a **new** Socket.IO event (e.g. `"submission_processed"`,
distinct from the dashboard's `"tally_updated"`) so the specific agent who
uploaded it finds out without polling.

**Why Cloud Tasks specifically, not a custom Redis queue** (Memorystore is
already provisioned and could technically serve this): Cloud Tasks has
per-queue `--max-concurrent-dispatches` / `--max-dispatches-per-second`
built in — that setting *is* the Anthropic-rate-limit throttle, with retry
and backoff handled for free. Rolling the same guarantee on top of Redis
means rebuilding what Cloud Tasks already does.

```bash
gcloud tasks queues create tally333-extraction-queue \
  --location=us-central1 \
  --max-concurrent-dispatches=5 \
  --max-dispatches-per-second=5
# Conservative placeholder, not sized against a real Anthropic limit — raise
# with `gcloud tasks queues update` once you know your actual tier's rate
# limit; no redeploy needed, the queue takes effect immediately.

gcloud iam service-accounts create tally333-tasks-invoker

# tally333-api's own runtime SA needs this to be allowed to mint OIDC
# tokens for tally333-tasks-invoker's identity when it creates a task —
# without it, CreateTask calls fail with a permission error.
gcloud iam service-accounts add-iam-policy-binding \
  tally333-tasks-invoker@PROJECT_ID.iam.gserviceaccount.com \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud run deploy tally333-extraction-worker \
  --image us-central1-docker.pkg.dev/PROJECT_ID/tally333/backend \
  --region us-central1 \
  --no-allow-unauthenticated \
  --add-cloudsql-instances PROJECT_ID:us-central1:tally333-db \
  --vpc-connector=tally333-connector \
  --set-secrets DATABASE_URL=tally333-db-url:latest,JWT_SECRET_KEY=tally333-jwt:latest,SECRET_KEY=tally333-secret:latest,ANTHROPIC_API_KEY=tally333-anthropic-key:latest \
  --set-env-vars "^;^SERVICE_ROLE=api;CV_BACKEND=claude;REDIS_URL=redis://10.237.108.179:6379/0;STORAGE_BACKEND=gcs;GCS_BUCKET_NAME=project-x-477317-tally333-forms" \
  --memory=2Gi --concurrency=1 --min-instances=0 --max-instances=5
# --concurrency=1 matches the "one worker holds one Claude call" model —
# Cloud Tasks' own dispatch concurrency is the real throttle, this just
# stops Cloud Run from being a second, uncoordinated one. --min-instances=0
# is fine here (unlike tally333-api/-realtime) — cold starts just mean a
# task takes a little longer, Cloud Tasks doesn't mind waiting.

gcloud run services add-iam-policy-binding tally333-extraction-worker \
  --region=us-central1 \
  --member="serviceAccount:tally333-tasks-invoker@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Then wire tally333-api to actually dispatch, instead of the inline fallback:
gcloud run services update tally333-api --region us-central1 \
  --update-env-vars "^;^GCP_PROJECT=PROJECT_ID;CLOUD_TASKS_LOCATION=us-central1;CLOUD_TASKS_QUEUE=tally333-extraction-queue;EXTRACTION_WORKER_URL=<worker-url>/internal/submissions/extract;TASKS_INVOKER_SERVICE_ACCOUNT=tally333-tasks-invoker@PROJECT_ID.iam.gserviceaccount.com"
```
`create_draft()`'s task-enqueue step (`google-cloud-tasks` dependency) uses
that same `tally333-tasks-invoker` service account's identity for the OIDC
token Cloud Tasks attaches when it calls the worker.

**Gotcha, again**: `--args` on `gcloud run jobs create`/`update` uses `,` as
its own delimiter too, same as `--set-env-vars` — a comma anywhere in a
`python -c "..."` script silently truncates it (Python only executes the
first arg as code; the rest become inert `sys.argv` entries, so the command
still exits `0` with no error, just does nothing). Same fix: gcloud's
alternate-delimiter syntax, `--args="^|^-c|<script>"`. Bit twice by the
`,`-delimiter issue in this session — once with `--set-env-vars`, once with
`--args` — worth checking any future `gcloud run` flag that accepts a list
before assuming a comma in the value is safe.

**Verified against the real deployment**, not just locally: a test upload
returned `202`/`"processing"` immediately, then resolved to `"draft"`
~16-20 seconds later — confirmed in `tally333-extraction-worker`'s own logs
(a `200` on `/internal/submissions/extract` from Cloud Tasks, followed by a
real `200` from `api.anthropic.com`), not just inferred from the final
polled state.

**Costly gotcha, worth real emphasis: `tally333-extraction-worker` is a
separate deployment from `tally333-api` and does not get redeployed by
"redeploy the backend."** They share one image, but each is its own Cloud
Run *service* with its own revision history — `gcloud run deploy
tally333-api` only ever updates `tally333-api`. This actually happened: the
multi-stream fix below shipped correctly to `tally333-api`, tests passed,
the migration applied — but `tally333-extraction-worker` was still serving
its original revision from the day it was first deployed, silently running
pre-fix extraction code for every real (async, Cloud-Tasks-dispatched)
upload. Votes/location extracted fine (that logic predated the fix), but
`stream_number` never updated, so the bug it was supposed to fix looked
completely unfixed in production despite every test and direct extraction
check passing. Caught only by testing the real end-to-end upload path
against real files, not by unit tests (which call `process_extraction()`
directly, bypassing Cloud Tasks and the worker entirely) or by trusting a
green `tally333-api` deploy. **Any change touching `app/services/extraction.py`,
`claude_vision.py`, `cv_pipeline.py`, or anything `_run_extraction()` calls
needs `tally333-api` *and* `tally333-extraction-worker` both redeployed —
check `gcloud run services describe tally333-extraction-worker --region=
us-central1 --format='value(status.latestReadyRevisionName)'` against the
just-built image if in doubt.**

### Frontend changes (implemented)

`UploadPage.tsx` shows a "Processing your upload…" state whenever the
`202` response comes back with `status: "processing"`, listens on the
existing `getSocket()` connection for `"submission_processed"` scoped to
that submission id, and falls back to polling `GET /api/submissions/:id`
(bounded — stops after a few minutes) in case the event's missed, then
transitions to the normal preview/confirm UI once resolved. `STATUS_LABEL`
has `processing` and `extraction_failed` entries. Locally (mock backend,
no Cloud Tasks queue configured) extraction still resolves inline before
the response is even sent, so this new state is invisible in local dev —
it only shows up against the real deployed queue.

### What this buys, and what it doesn't

It doesn't make Claude process 25,000 images any faster — nothing beats
Anthropic's actual sustainable throughput for this API key. What it buys is
**graceful degradation instead of failure**: a burst past that ceiling
means agents see "processing" for longer while Cloud Tasks works through
the backlog at a safe, controlled rate, instead of Cloud Run instances
compounding memory pressure or Anthropic returning 429s that just fail the
upload outright. Cloud Run sizing for both services only becomes a sane
question *after* this split — right now `tally333-api`'s worker count and
memory are entangled with Claude's latency in a way that makes any instance
math for "25,000 concurrent" a guess dressed up as a number.

## Database — Cloud SQL

```bash
gcloud sql instances create tally333-db \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-g1-small \
  --region=us-central1 \
  --availability-type=REGIONAL \
  --storage-auto-increase
gcloud sql databases create tally333 --instance=tally333-db
```

**Gotcha:** new GCP projects now default Cloud SQL to the Enterprise Plus
edition, which rejects legacy shared-core tier names like `db-g1-small`
(`Invalid Tier ... for ENTERPRISE_PLUS Edition`). Pass `--edition=ENTERPRISE`
explicitly to use it. `--availability-type=REGIONAL` adds a standby replica
with automatic failover — worth it here since this instance holds actual
vote-tally data, unlike the disposable Redis pub/sub layer above; omit it
(defaults to zonal) for a cheaper non-production instance.

This is already provisioned (see the intro) as `tally333-db`; the app user
`tally333` and its generated password are in Secret Manager as
`tally333-db-url`, not in this file.

Connect from Cloud Run via the Cloud SQL Auth Proxy sidecar (the
`--add-cloudsql-instances` flag above wires this up automatically) using a
Unix socket `DATABASE_URL`:

```
postgresql+psycopg2://tally333:PASSWORD@/tally333?host=/cloudsql/PROJECT_ID:us-central1:tally333-db
```

Run `flask --app wsgi db upgrade` as a one-off Cloud Run job (or via
`gcloud sql connect` + local `flask db upgrade` against the proxy) after each
deploy that changes the schema.

**Applied to production**: migration `35653319bd80` adds
`form_submission.stream_number` — a polling station can be split into
multiple independent streams (separate ballot box, presiding officer, Form
34A per stream; the printed form header shows e.g. "POLLING STATION 3 of
4"), and without this column, `app/services/dedup.py` was treating a
second stream's finalized submission as a *correction* of the first,
silently dropping its votes from the tally instead of adding to them.
Dedup/supersede now keys on `(station_id, form_type, stream_number)`
instead of just `(station_id, form_type)`; Claude Vision reads the stream
indicator off the form header automatically (`app/services/claude_vision.py`),
with no change to the agent-facing station picker. Verified via two new
backend tests (`test_different_streams_of_the_same_station_both_count_instead_of_superseding`,
`test_votes_by_station_shows_a_separate_row_per_stream_of_the_same_station`)
and a local migration dry-run against a real Postgres with existing rows.

**Update — re-verified end-to-end against real production data**: the fix
initially appeared broken in real use (reported: uploading real streams "1
of 2" and "2 of 2" of the same station still overrode). Root cause was a
deployment gap, not a logic bug — see the `tally333-extraction-worker`
gotcha above. After redeploying the worker, re-uploading two real Form 34A
files (`F34A-046-273-1362-003-01.PDF` / `-02.PDF`, Nyagacho Primary School,
Nyamira) through the live API confirmed both streams resolve correctly
(`stream_number` 1 and 2), both finalize to `auto_approved`, neither
supersedes the other, and `votes_by_station` shows them as two separate
rows.

**Also found and fixed while investigating**: `app/services/location_check.py`'s
station-name matching was too lenient for short names — "Ensakia Primary
School" and a real form reading "Nyagacho Primary School Polling Station 1
of 2" shared only the generic words "Primary School" but crossed the old
50%-of-shorter-set overlap threshold anyway, so a genuinely wrong station
selection wasn't being caught. Fixed by excluding a list of common
institution-type/boilerplate words (`_GENERIC_TOKENS` — PRIMARY, SCHOOL,
POLLING, STATION, TBC, etc.) and pure-digit tokens (stream indicators like
the "1"/"2" in "1 of 2" don't identify a place) from the overlap
calculation, so a partial match now has to share an actual distinguishing
word, not just boilerplate. A name that's a strict subset/superset of the
other (the common real case — a verbose form header containing a shorter
stored name) still matches unconditionally, unaffected. Two new tests in
`backend/tests/test_location_check.py` cover the exact false-positive case
and confirm short genuine matches still work.

## Populating geography data

The county/constituency/ward/polling-station hierarchy isn't something to
export from a local database and import into Cloud SQL — it's static
reference data, already checked into the repo as
`backend/seed_data/kenya_geography.json` (MIT-licensed, sourced from
github.com/stevehoober254/kenya-county-data — see the docstring in
`backend/import_geography.py`) and already baked into the deployed
container image. So it's loaded the same way in every environment, local
or prod, with the same command — no data transfer between environments
needed:

```bash
gcloud run jobs create tally333-geo-import \
  --image us-central1-docker.pkg.dev/PROJECT_ID/tally333/backend \
  --region us-central1 \
  --set-cloudsql-instances PROJECT_ID:us-central1:tally333-db \
  --set-secrets DATABASE_URL=tally333-db-url:latest,JWT_SECRET_KEY=tally333-jwt:latest,SECRET_KEY=tally333-secret:latest \
  --set-env-vars CV_BACKEND=mock \
  --command flask \
  --args="--app,wsgi,import-geography" \
  --task-timeout=900 \
  --max-retries=0
gcloud run jobs execute tally333-geo-import --region us-central1 --wait
```

`flask --app wsgi import-geography` (`backend/import_geography.py`) seeds
47 counties, 290 constituencies, ~1,450 wards, ~24.6k polling stations, and
all 6 elective positions (president, MP, MCA, governor, senator, woman
rep) in one pass — that single command was previously missing from the
deployed database, which is why `/api/positions` returned `[]` earlier.
It's idempotent: it checks `County.query.first()` and skips entirely if
geography is already imported, so re-running `tally333-geo-import` (e.g.
after a redeploy) is always safe. `PollingStation.iebc_code` stays `null`
everywhere except Nyamira's ~332 stations, and even there only if a local
Form 34A PDF directory happens to be present on the machine running the
import (it isn't, in Cloud Run) — fine for display/selection, don't build
anything that assumes it's always populated.

Already run against `tally333-db` (see the intro) — the job
`tally333-geo-import` is left in place (like `tally333-db-migrate`) for
reuse, e.g. if the database is ever reset.

## Form images — Cloud Storage

**Implemented and deployed** (see the intro). `backend/app/services/storage.py`
gained a `GCSStorage` class — but it's *not* a drop-in swap for
`LocalStorage`, because `looks_blank()` (`app/services/image_quality.py`)
and Claude Vision's `_prepare_image()` (`app/services/claude_vision.py`)
both call `PIL.Image.open()` on a real local filesystem path. So processing
(blank check → CV extraction → dedup check) still happens against a local
temp file exactly as before — Cloud Run's ephemeral disk is genuinely fine
for that, within one request's lifetime. Only *persistence* changed:
`create_draft()` (`app/api/submissions.py`) uploads the validated image to
GCS and deletes the local temp copy right before creating the
`FormSubmission` row, so `image_path` becomes a GCS object name (the
sha256 + extension — deterministic, so re-uploading identical bytes just
overwrites) rather than a filesystem path, gated behind
`STORAGE_BACKEND == "gcs"` (env var, defaults to `"local"` — local dev and
tests are unaffected).

`GET /api/submissions/:id/image` **streams the blob through Flask** rather
than redirecting to a signed URL — the deliberate choice here, over the
docs' original suggestion of either. The existing JWT + ownership/role
check in that handler runs on every single fetch this way; a signed URL
would stay valid for its full expiry window even if the requester's access
changed in that window, which matters for access-controlled election-result
images. Cost: a little more `tally333-api` bandwidth/CPU per image fetch,
negligible at this app's scale.

Bucket: `project-x-477317-tally333-forms` (regional, `us-central1`, uniform
bucket-level access). IAM is scoped to just this bucket rather than
project-wide:
```bash
gcloud storage buckets create gs://project-x-477317-tally333-forms \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding gs://project-x-477317-tally333-forms \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

## CDN and Cloud Armor

**Provisioned** (see the intro), fronting `tally333-api` only —
`tally333-realtime` stays on its direct Cloud Run URL, since a CDN in front
of long-lived Socket.IO connections doesn't make sense. Chain, built in
this order because each piece references the previous by name:

```bash
gcloud compute addresses create tally333-lb-ip --global

gcloud compute network-endpoint-groups create tally333-api-neg \
  --region=us-central1 --network-endpoint-type=serverless \
  --cloud-run-service=tally333-api

gcloud compute backend-services create tally333-api-backend \
  --global --load-balancing-scheme=EXTERNAL_MANAGED --enable-cdn
gcloud compute backend-services add-backend tally333-api-backend \
  --global --network-endpoint-group=tally333-api-neg \
  --network-endpoint-group-region=us-central1

gcloud compute url-maps create tally333-api-urlmap \
  --default-service=tally333-api-backend

gcloud compute ssl-certificates create tally333-api-cert \
  --domains=<ip-with-dashes>.nip.io --global

gcloud compute target-https-proxies create tally333-api-https-proxy \
  --url-map=tally333-api-urlmap --ssl-certificates=tally333-api-cert

gcloud compute forwarding-rules create tally333-api-https-rule \
  --address=tally333-lb-ip --global \
  --target-https-proxy=tally333-api-https-proxy --ports=443

gcloud compute security-policies create tally333-armor-policy \
  --description="Rate limiting for tally333-api"
gcloud compute security-policies rules create 1000 \
  --security-policy=tally333-armor-policy --src-ip-ranges="*" \
  --action=throttle --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 --conform-action=allow \
  --exceed-action=deny-429 --enforce-on-key=IP

gcloud compute backend-services update tally333-api-backend \
  --global --security-policy=tally333-armor-policy
```

**No custom domain yet** — a Google-managed SSL cert needs a real domain
that resolves to the LB's static IP to validate. Rather than block on
that, this used a **nip.io wildcard domain**: `<ip-with-dashes>.nip.io`
resolves to that exact IP automatically (no DNS record needed), which is
enough for Google's managed-cert validation to succeed against the real
reserved IP. Swapping in a real domain later is additive, not a redo: add
it to the same cert (`gcloud compute ssl-certificates create` a new one, or
recreate with multiple `--domains`), point its DNS A record at the
reserved IP (`gcloud compute addresses describe tally333-lb-ip --global`),
and update the target HTTPS proxy once that cert is `ACTIVE`.

**Cloud CDN is genuinely caching now, implemented as of this write-up.**
`app/utils/caching.py` has one small decorator:
```python
def cache_control(value: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            resp = make_response(fn(*args, **kwargs))
            resp.headers["Cache-Control"] = value
            return resp
        return wrapper
    return decorator
```
Applied only to unauthenticated GET routes — a shared cache like Cloud CDN
doesn't vary its cache by the `Authorization` header by default, so this
must never touch an endpoint that returns per-user or role-gated data
(`submissions.py`'s routes are all JWT-gated and correctly untouched):
- `geography.py`, `positions.py` — `public, max-age=3600`. Static
  reference data, only ever changes via the one-time
  `import-geography` CLI command.
- `tally.py` — `public, max-age=5`. Live results, matching "Cache the
  read-only path at the edge" in "Scaling to 50,000 concurrent users"
  above — tolerates a few seconds of staleness in exchange for absorbing
  a traffic spike at the edge instead of hitting Postgres per request.

Verified as real caching, not just a correctly-set header: two requests a
second apart through the LB showed the `Age` response header actually
incrementing (`9` → `11`), meaning Cloud CDN served the second one from
its own cache rather than re-fetching from `tally333-api`.

**The frontend now routes through this LB** — `VITE_API_URL` points at
`https://8-232-246-179.nip.io`, not `tally333-api`'s own `run.app` URL
(rebuilt + redeployed to Firebase Hosting; see the `VITE_API_URL` gotcha
below). `VITE_SOCKET_URL` stays pointed directly at `tally333-realtime` —
no LB in front of long-lived Socket.IO connections. CORS preflight through
the LB from the deployed frontend's real origin was verified working, not
just assumed.

## Frontend — Firebase Hosting (recommended) or Cloud Run

Firebase Hosting is a better fit than another Cloud Run service for a static
SPA build: free CDN, no cold starts, simpler custom-domain setup.

**Already deployed** — live at https://project-x-477317.web.app. What was
actually run, non-interactively (`firebase init hosting`'s prompts were
answered by hand-writing the two files it would have generated):

```bash
cd frontend
# frontend/.firebaserc: { "projects": { "default": "project-x-477317" } }
# frontend/firebase.json: public "dist", rewrite "**" -> "/index.html"
echo 'VITE_API_URL=https://8-232-246-179.nip.io'                             > .env.production.local
echo 'VITE_SOCKET_URL=https://tally333-realtime-82161509094.us-central1.run.app' >> .env.production.local
# VITE_API_URL is the load balancer (CDN + Cloud Armor in the request path),
# not tally333-api's own URL — see "CDN and Cloud Armor" above. Sockets stay
# direct to tally333-realtime; there's no LB in front of them.
npm run build
firebase deploy --only hosting --project project-x-477317
```

`.env.production.local` matches the `*.local` gitignore pattern already in
`frontend/.gitignore` — Vite loads it automatically for `npm run build`
(mode `production`) without touching the shared `frontend/.env`.

**Gotcha:** `firebase projects:addfirebase PROJECT_ID` (needed once, before
`firebase deploy` works on a GCP project that was never a Firebase project)
can time out client-side after ~30s while the operation is still running
server-side — the CLI reports failure, but retrying the same command then
correctly returns `409 ALREADY_EXISTS`, confirming it had actually
succeeded. Don't assume a timeout here means nothing happened; re-run the
command once to check before troubleshooting further.

Set `VITE_API_URL` to the deployed Cloud Run backend URL at build time
(it's baked into the JS bundle — see the gotcha below).

If you'd rather keep everything on Cloud Run (one platform, one billing
surface), `frontend/Dockerfile` already builds and serves via nginx — deploy
it the same way as the backend, just without `--add-cloudsql-instances`.

## Gotcha: `VITE_API_URL` (and `VITE_SOCKET_URL`) are baked in at build time

Vite replaces `import.meta.env.VITE_API_URL` and `VITE_SOCKET_URL` with
literal strings during `npm run build` — neither is read at runtime. If a
backend URL changes (new environment, new custom domain, or — at the
50,000-user split — pointing `VITE_SOCKET_URL` at `tally333-realtime`
instead of `tally333-api`), the frontend must be rebuilt, not just
redeployed with a different env var. `docker-compose.yml`'s
`frontend.build.args` shows the same thing locally: changing either value
requires `docker compose build frontend` again, not just `up`.

## Secrets

```bash
echo -n "postgresql+psycopg2://..." | gcloud secrets create tally333-db-url --data-file=-  # already created
echo -n "$(openssl rand -hex 32)" | gcloud secrets create tally333-jwt --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create tally333-secret --data-file=-
echo -n "sk-ant-..." | gcloud secrets create tally333-anthropic-key --data-file=-
```

`tally333-db-url` exists already, created alongside the Cloud SQL instance
above. The other three are still just the plan.

Never commit `backend/.env` — `.gitignore` already excludes it.

## Not yet covered here

- OTP delivery is real (SMTP, `app/services/email.py`) and confirmed working
  on the deployed `tally333-api` (see the intro) — but only verified at
  single-email scale, not election-day volume. Gmail's SMTP sending limits
  are the concern at real volume, not code correctness — a transactional
  email provider (SendGrid, SES) or a real SMS channel (e.g. Africa's
  Talking) may be worth adding as a fallback before go-live.
- Candidate name matching is exact-normalized only (`app/services/candidates.py`)
  — no fuzzy matching. If Claude Vision reads the same candidate's name
  inconsistently across forms, they'll show up as separate candidates. Worth
  monitoring once real data starts flowing; not solved preemptively.
- CDN/WAF in front of the backend (Cloud Armor, if public-facing) — see
  "Scaling to 50,000 concurrent users" above for the plan once this is
  needed.
- The upload path is now async and provisioned end-to-end (see "Async form
  extraction" above), but `tally333-extraction-queue`'s concurrency
  (`--max-concurrent-dispatches=5`) is a conservative placeholder, not
  sized against this project's actual Anthropic rate limit — raise it once
  that's known.
- The IEBC portal comparison job (Section 08 of the original spec) — not
  implemented; would run as a Cloud Scheduler + Cloud Run job once there's a
  source to pull official results from.
- `iebc_code` is null for all but Nyamira's ~332 imported polling stations —
  the national dataset (`backend/seed_data/kenya_geography.json`) has no
  official codes, only names. Fine for display/selection; don't build
  anything that assumes it's always present.
