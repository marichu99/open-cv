// k6 load test for tally333-extraction-worker's internal endpoint,
// bypassing Cloud Tasks entirely — see docs/LOAD_TEST_PLAN.md for why, and
// for the seeding step (loadtest/seed_submissions.py) this script depends on.
//
// Usage:
//   TOKEN=$(gcloud auth print-identity-token \
//     --impersonate-service-account=tally333-tasks-invoker@project-x-477317.iam.gserviceaccount.com)
//   k6 run \
//     -e WORKER_URL=https://tally333-extraction-worker-xxxx.us-central1.run.app \
//     -e OIDC_TOKEN=$TOKEN \
//     -e SUBMISSION_IDS_FILE=./submission_ids.json \
//     loadtest/extraction_worker.js
//
// Track A (CV_BACKEND=mock) can raise MAX_RATE well past Track B's — there's
// no external rate limit to find, only Cloud Run/DB/GCS ceilings.

import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';

const WORKER_URL = __ENV.WORKER_URL;
const OIDC_TOKEN = __ENV.OIDC_TOKEN;
if (!WORKER_URL || !OIDC_TOKEN) {
  throw new Error('WORKER_URL and OIDC_TOKEN env vars are required');
}

const submissionIds = new SharedArray('submissions', function () {
  return JSON.parse(open(__ENV.SUBMISSION_IDS_FILE || './submission_ids.json'));
});

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 400,
      // Track B stages — see docs/LOAD_TEST_PLAN.md's table. Watch Cloud
      // Logging live and Ctrl-C the run once the 429 rate climbs; don't
      // wait for later stages to finish once the wall is found.
      stages: [
        { target: 1, duration: '1m' },
        { target: 5, duration: '3m' },
        { target: 10, duration: '3m' },
        { target: 20, duration: '3m' },
        { target: 40, duration: '3m' },
        { target: 80, duration: '3m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  // Globally unique across every VU/iteration in the scenario — each
  // seeded submission is consumed exactly once. Reusing an id after it's
  // already flipped out of "processing" would make process_extraction()
  // return early (fast 200, no Claude call), silently inflating apparent
  // throughput — see the seeding note in docs/LOAD_TEST_PLAN.md.
  const idx = exec.scenario.iterationInTest;
  if (idx >= submissionIds.length) {
    throw new Error(
      `ran out of seeded submissions (${submissionIds.length}) at iteration ${idx} — ` +
      're-seed with headroom above the sum of rate*duration across all stages'
    );
  }
  const submissionId = submissionIds[idx];

  const res = http.post(
    `${WORKER_URL}/internal/submissions/extract`,
    JSON.stringify({ submission_id: submissionId }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OIDC_TOKEN}`,
      },
      timeout: '60s',
    }
  );

  check(res, {
    'status is 200': (r) => r.status === 200,
    'not rate-limited': (r) => r.status !== 429 && r.status !== 500,
  });
}
