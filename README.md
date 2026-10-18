# Whistles

Whistles is a risk radar for a bank's public voice. It reads what customers, scammers, regulators
and the press say about a bank on public channels, scores that conversation for fraud, complaint
escalation, churn and service incidents, helps a care team respond, and measures whether the
response worked.

Built for the Hack2skill AI Builder Cup 2026, BFSI track: Intelligent Risk, Fraud & Financial Experiences.

**Live demo:** https://guru-web-56603861230.asia-southeast1.run.app
The demo needs a sign-in; reviewers receive the credentials with the submission.

**Demo data:** every bank, rival, regulator, customer and post in the demo is invented. The demo
tenant is "Lumora Bank", a fictional institution, and its data is synthetic. Collectors are
switched off for it, so no real data is mixed in.

## What it does

| Job | What you get |
| --- | --- |
| Detect | Scam signals on the bank's own pages, incident radar, complaint triage, switch intent, regulatory watch, branch and ATM feed |
| Act | Care console with Gemini-drafted replies, SLA tracking, supervisor view, held-reply approvals, macros, case routing |
| Prevent | Content calendar that proposes posts from live signals, with a compliance check before publishing |
| Prove | Before and after impact for every post, with confidence intervals |

## How it works

```text
Browser
  -> guru-web   Next.js 16 (Cloud Run), proxies /api/*
       -> guru-api   FastAPI, one always-on instance (Cloud Run)
            |-- Cloud SQL for PostgreSQL 16   cases, mentions, content, audit; row-level security
            |-- Vertex AI (Gemini 2.5 Flash)  reply drafts, rewrites, AI-visibility panel
            '-- Secret Manager                database URL, app secrets, passwords

GitHub push to main -> Cloud Build -> Artifact Registry -> Cloud Run (about 10 minutes)
```

- The API is a FastAPI app. A small Flask shell is mounted behind it for health probes and static
  assets. The job worker and the scheduler run inside the API process, which is why the service
  runs as a single instance with CPU always allocated.
- Tenancy is enforced in the database. Each workspace is a tenant, every table carries its
  workspace, and Postgres row-level security applies to the application role. A separate operator
  role bypasses it for migrations and the seed job.
- Gemini is called over plain HTTP using the Cloud Run service account, so there is no API key in
  the code or the config. Set `GURU_LLM=vertex` to turn it on; the project comes from
  `GOOGLE_CLOUD_PROJECT` or the metadata server, the model from `VERTEX_MODEL`.
- Sessions live in Redis when `REDIS_URL` is set and in process memory otherwise.

## Where Gen AI is used, and where it is not

Gen AI is used for text a person reads and then sends or ignores:

- reply drafts and rewrites in the care console
- post drafts, caption help and compliance rewrites in the content calendar
- the AI-visibility panel, which asks several models the same questions about the brand and keeps
  the raw answers as evidence (Gemini through Vertex AI; the other models need an OpenRouter key)
- sentiment on text a lexicon cannot settle (a hosted classifier, only for the ambiguous cases)

Gen AI does not produce any risk score. Scam, escalation, churn and switch-intent scores are
fixed-weight rules, incident detection is a statistical test, and impact is measured with
confidence intervals. A model can draft a reply; it cannot change a score.

## Scoring

Every score traces to a rule you can read.

- **Scam signals.** Each distinct signal in a comment adds a fixed weight: WhatsApp contact 4,
  phone number 3, shortened link 3, Telegram handle 3, payout or prize lure 2, off-channel contact
  lure 2, support impersonation 2. Severity bands: high at 7 or more, elevated at 4, low at 1.
  See `apps/api/core/scam.py`.
- **Complaint triage.** Text rules (regulator named 4, legal action 3, unrecovered loss 3, threat
  to go public 2, vulnerable customer 2, unresolved or repeat contact 2, account access blocked 2,
  churn language 1) plus context rules (classified as fraud, one-star and two-star reviews,
  negative sentiment). Bands: critical at 8 or more, high at 5, elevated at 3, watch at 1.
  See `apps/api/core/triage.py`.
- **Incident radar.** Mention velocity per brand against a trailing 28-day baseline. A spike
  needs a z-score of at least 2.5, at least 4 mentions a day, and 30 percent of the spike's
  mentions matching incident-shaped keywords. See `apps/api/core/incidents.py`.
- **Did it help.** Proportions use Wilson 95 percent intervals over the 7 days before and after a
  post, with at least 10 comments in each window. A post counts as improved only when the
  intervals do not overlap, and the panel says the result is an association, not proof.

## Run it locally

Requirements: Python 3.12, Node 22, Docker (for Postgres and Redis).

```bash
npm run db:up                        # Postgres 16 and Redis from ops/compose/docker-compose.yml
pip install -r apps/api/requirements.txt
npm install
npm run migrate                      # alembic upgrade head

# Load the fictional Lumora Bank tenant. Pick your own password for the demo logins.
cd apps/api
DEMO_PASSWORD='choose-a-password' python scripts/seed_demo_bank.py --reset --drop-default-workspace
cd ../..

npm run dev                          # API on :5000, web on :3000
```

Open http://127.0.0.1:3000 and sign in as `demo.admin` with the password you chose. The other
seeded logins are `farah.supervisor`, `kamran.lead`, `zainab.senior`, `hira.agent` and
`lumora.viewer`. The database defaults to `postgresql+psycopg://guru:guru@localhost:5432/guru`;
override it with `DATABASE_URL`. To use Gemini locally, set `GURU_LLM=vertex` with application
default credentials and a project that has the Vertex AI API enabled.

Seed dates are relative to the day you run the script, so re-run it before a demo.

## Tests

```bash
npm run check:api    # backend suite (needs Postgres from npm run db:up)
npm run check:web    # typecheck, lint, production build
npm run test:e2e     # Playwright journeys (run npm run test:e2e:install once)
```

## Deploy to Google Cloud

`deploy/gcp/README.md` walks through the first deploy: Cloud SQL, Secret Manager, Artifact
Registry and two Cloud Run services. After that, a Cloud Build trigger runs
`deploy/gcp/cloudbuild-deploy.yaml` on every push to `main`: it builds both images, deploys
`guru-api`, then builds the web image against the API's address and deploys `guru-web`.

## Repository layout

```text
apps/api            FastAPI service: routers, scoring, collectors, jobs, migrations, tests
apps/web            Next.js 16 app
packages/contracts  OpenAPI contract the web types are generated from
deploy/gcp          Dockerfile-based Cloud Build configs and the deploy guide
ops/compose         Local Postgres and Redis
docs                Design notes and operating guides
```

## Known limits

- Collectors run on seeded data in the demo. Live collectors for X, Meta and review sites exist
  in `apps/api/integrations` and need their own credentials.
- Uploaded images are stored on the container's disk and are lost on redeploy. Use a Cloud Storage
  bucket for anything permanent.
- Workers run inside the API process. Splitting them into a separate service is the next step
  toward streaming collection.
- Seed and test accounts use development passwords by default. Set real values through
  `GURU_ADMIN_PASSWORD`, `GURU_VIEWER_PASSWORD` and `DEMO_PASSWORD` for anything reachable from the
  internet; the Cloud Run deployment reads them from Secret Manager.
