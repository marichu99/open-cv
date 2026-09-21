# k6 load test plan — `tally333-extraction-worker`

## What this is actually measuring, and why it has to bypass Cloud Tasks

The question this test exists to answer: **what's the real sustainable
throughput of one Claude Vision call path, per API key** — the number
`docs/DEPLOYMENT.md` explicitly says nobody has measured
("`tally333-extraction-queue`'s concurrency being sized against a real
Anthropic rate limit rather than the conservative placeholder of 5" is
listed as "not provisioned yet").

That number can't be observed by load-testing the public upload endpoint
(`POST /api/submissions`) — Cloud Tasks sits in between and enforces
`--max-concurrent-dispatches=5` / `--max-dispatches-per-second=5`
regardless of how much load you throw at it. Uploads would just queue
further back; the worker would never see more than 5 concurrent calls, and
you'd learn nothing about the real ceiling.

So this test hits `tally333-extraction-worker`'s internal endpoint
(`POST /internal/submissions/extract`) **directly**, skipping Cloud Tasks
entirely. That endpoint is `--no-allow-unauthenticated` and additionally
verifies a Google-signed OIDC token bound to the
`tally333-tasks-invoker` service account (`app/api/internal.py`) — so the
test needs to mint tokens for that identity (see Auth, below).

Once the real per-key ceiling is known, `tally333-extraction-queue`'s
dispatch limits and `tally333-extraction-worker --max-instances` get set
to match it (or to `N × per-key limit` once keys are sharded) — that's the
whole point of running this.

## ⚠️ Do not point this at the production database as-is

`process_extraction()` (`app/services/extraction.py`) commits real rows:
it creates `Candidate`/`VoteRecord` rows via `get_or_create_candidate()`
and flips the seeded `FormSubmission` to `status="draft"`. Draft
submissions surface in a coordinator's review queue and, once
approved, in real result aggregates. Running this test against
`project-x-477317`'s live Cloud SQL instance pollutes real election data
with load-test garbage — there is currently no "test mode" flag anywhere
in this pipeline that suppresses that.

Before running anything beyond the smoke stage (below), pick one:

1. **Preferred**: clone the stack into a second GCP project (or at least a
   second Cloud SQL instance + GCS bucket) sharing nothing with
   `project-x-477317`, seeded the same way (`flask import-geography`).
   Point `tally333-extraction-worker`'s env vars at that clone for the
   duration of the test.
2. **If a clone isn't feasible in time**: only ever run this against a
   throwaway `tally333-extraction-worker` *revision* deployed with
   `CV_BACKEND=mock` (see Track A below) pointed at the real DB, and
   restrict any real-Claude run (Track B) to the smoke stage's ~20
   requests, then delete the seeded rows and their `VoteRecord`s
   afterward with a cleanup script keyed off a `agent_id` reserved for
   load-test seeding (the seed script below tags them this way
   specifically so they're identifiable and deletable).

Never run Track B's ramp stages against production data.

## Two tracks

Claude Vision billing and Anthropic's rate limit are the thing actually
being investigated, so it's worth separating "can GCP infra keep up" from
"what does Claude sustain" — conflating them means a Cloud SQL write bottleneck
looks like an Anthropic rate limit, or vice versa.

**Track A — infrastructure ceiling (cheap, safe to run at full scale).**
Deploy a throwaway `tally333-extraction-worker` revision with
`CV_BACKEND=mock` (`MockExtractionService` — deterministic, no network
call, no billing). This isolates Cloud Run cold starts/autoscaling,
Cloud SQL write throughput, and GCS download latency from the Claude call
itself. Run this first and at real target scale (thousands of concurrent
requests) — it's free and tells you whether anything *other* than
Anthropic's rate limit would cap throughput first (e.g. Cloud SQL
`max_connections`, per the "won't hold at this scale" warning on
`db-g1-small` in `docs/DEPLOYMENT.md`).

**Track B — real Claude ceiling (billed, deliberately bounded).**
Same worker, `CV_BACKEND=claude`, real `ANTHROPIC_API_KEY`(s). This is
the one that answers "what's the real number." Ramp slowly and stop the
instant the error rate (429s surfacing as 5xx from the worker) crosses a
threshold — that inflection point *is* the answer. Budget for it: even a
few hundred real Sonnet-5 vision calls costs real money (see
`claude_vision.py`'s per-call cost logging — `cost_usd` is written to the
logs for every call, so actual spend for the run is directly readable
from Cloud Logging afterward, not estimated).

## Test data

`process_extraction()` needs a real `FormSubmission` row with
`status="processing"`, a valid `image_path` already in GCS, and FKs to a
real `station_id`/`agent_id`/`position_id` — it does not go through
`create_draft()`'s `looks_blank()`/dedup checks (those are Phase-1-only),
so seeding rows directly into Postgres + one image into GCS is enough;
no multipart upload flow needed.

The `(station_id, form_type, image_sha256)` unique constraint means the
*same* test image can be reused for every row for free, as long as each
row gets a distinct `station_id` — the geography seed already provides
~24,600 polling stations, comfortably more than any single test run needs.

`loadtest/seed_submissions.py` (below):
- uploads one sample form image to GCS once, computing its sha256
- creates one reusable load-test `Agent` (email tagged
  `loadtest@tally333.internal` so it's identifiable/deletable later)
- for `--count` N, inserts N `FormSubmission` rows in `status="processing"`,
  round-robining across real seeded stations/one position, all pointing at
  the same GCS object
- writes the generated submission ids to a JSON file the k6 script reads

Run it as a one-off Cloud Run Job against the target DB/bucket (same
pattern as `tally333-gcs-check` in `docs/DEPLOYMENT.md`), not from a
laptop, so it uses the same service-account credentials path.

**Seed at least as many rows as the maximum possible total iterations
across every stage of the k6 run, with ~25% headroom.** Each submission
row can only be consumed once — `process_extraction()` returns early
(fast, HTTP 200, no Claude call) the moment `status != "processing"`, so
reusing an id after it's been processed silently produces a fast fake
success that would make throughput look artificially high. The k6 script
below indexes ids by `k6/execution`'s `scenario.iterationInTest` (globally
unique across all VUs) specifically to avoid this — but only if enough
ids were seeded in the first place.

## Auth: minting OIDC tokens for the Cloud Tasks invoker identity

`_verify_cloud_tasks_oidc()` accepts any token signed for
`tally333-tasks-invoker@project-x-477317.iam.gserviceaccount.com`
(`audience` isn't checked — see the comment in `internal.py` explaining
why). Whoever runs the test needs
`roles/iam.serviceAccountTokenCreator` on that service account, then:

```bash
TOKEN=$(gcloud auth print-identity-token \
  --impersonate-service-account=tally333-tasks-invoker@project-x-477317.iam.gserviceaccount.com)
```

Identity tokens are valid for ~1 hour. For a run under an hour, mint once
and pass it in as `k6 run -e OIDC_TOKEN=$TOKEN`. For longer soak runs,
wrap the `k6 run` in a small script that re-mints and passes a fresh token
via k6's `setup()`/environment on each stage, or re-run per stage.

## k6 scenario design

Each request holds the HTTP connection for the full Claude Vision round
trip (several seconds, per the ~16-20s end-to-end figure already observed
through the real queue in `docs/DEPLOYMENT.md` — that included Cloud
Tasks dispatch latency, so the direct-to-worker number will likely be
lower, but still multi-second). A plain closed-loop VU model conflates
"requests per second" with "how many VUs happen to be blocked waiting" —
use `ramping-arrival-rate` instead so the *offered rate* is the
independent variable and k6 auto-allocates however many VUs it takes to
sustain it (up to `maxVUs`), which is what actually answers "how many
concurrent forms can this take."

Stages (Track B — adjust `target` for Track A, which can go much higher
since there's no external rate limit to find):

| Stage | Target rate | Duration | Purpose |
|---|---|---|---|
| 1 | 1 req/s | 1 min | Baseline single-call latency, sanity check |
| 2 | 5 req/s | 3 min | Matches today's provisioned queue limit — should be clean |
| 3 | 10 req/s | 3 min | First real probe past current config |
| 4 | 20 req/s | 3 min | |
| 5 | 40 req/s | 3 min | |
| 6 | 80 req/s | 3 min | Expect to find the wall around here or earlier — stop the run manually once error rate crosses ~5%, don't wait for the stage to finish |

Watch live during the run (`gcloud logging tail` on the worker, filtered
for `anthropic.APIError`, plus Cloud Run's own concurrency/instance-count
metrics) rather than only reading k6's summary after the fact — the goal
is to catch the exact stage where 429s start, not just confirm they
happened somewhere.

## Metrics to capture

- **k6**: `http_req_duration` (p50/p95/p99), `http_req_failed` rate, per
  stage.
- **Cloud Run** (`tally333-extraction-worker`): active instance count over
  time (does it actually scale to `--max-instances`, and how fast),
  container CPU/memory, request concurrency.
- **Anthropic**: 429 rate from the worker's own error logs
  (`claude_vision.py` re-raises `anthropic.APIError` as an `ApiError` the
  worker surfaces as a 5xx) — this rate crossing zero is the actual
  answer to "what's the ceiling."
- **Cost**: sum of `cost_usd` from `claude_vision.py`'s per-call log line
  across the run (Track B only).
- **Cloud SQL**: connection count, to catch `max_connections` exhaustion
  as a false-positive "rate limit" (Track A should catch this first,
  since it isolates DB/GCS from Claude entirely).

## Prerequisites checklist before running Track B for real

- [ ] Confirmed which DB/bucket the test is pointed at, and that it is
      **not** production (or accepted the cleanup-script fallback above)
- [ ] `roles/iam.serviceAccountTokenCreator` on `tally333-tasks-invoker`
      granted to whoever runs `k6`
- [ ] Track A run completed first, infra ceiling (if any, below the
      Anthropic wall) already known
- [ ] Hard budget agreed for Track B's Anthropic spend
- [ ] Someone watching Cloud Logging live during the run, not just the
      k6 summary afterward
