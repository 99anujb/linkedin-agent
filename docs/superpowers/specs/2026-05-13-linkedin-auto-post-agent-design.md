# LinkedIn Auto-Post Agent — Design

**Date:** 2026-05-13
**Owner:** Anuj Bansal (99anujbansal@gmail.com)
**Status:** Approved for implementation planning

---

## 1. Goal

Build an AI agent that drafts and posts daily LinkedIn content tailored to Anuj's profile (MS Data Science, ~4 years EdTech growth analytics, targeting Business Analyst / Data Analyst / Data Scientist roles in the US). The agent generates one post per day at 11:00 ET, Monday–Sunday, with human approval gating every post via email.

Primary success criteria:

- Posts go out 7 days a week at 11:00 ET (Buffer-scheduled).
- Every post is reviewed by Anuj before scheduling (human-in-the-loop).
- Content is on-brand: metric-heavy, technical-but-accessible, sourced from real profile data and verifiable external feeds.
- Setup is low-maintenance: secrets in one place, no servers to babysit, free-tier hosting.

Out of scope (for now):

- Posting to LinkedIn company pages or to other accounts.
- Real-time DM / comment automation.
- Multi-language posts.

---

## 2. Stack decisions (locked)

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | ML/data library ecosystem, Anthropic SDK first-class |
| Cron / runtime | GitHub Actions | Free 2,000 min/mo, native cron, no server to manage |
| Approval click handler | Cloudflare Workers | Free 100K req/day, can call GitHub Actions API to dispatch workflows |
| Approval delivery | Gmail SMTP + app password | Free, 500 sends/day, no third-party email service to wire up |
| LinkedIn posting | Buffer free tier | Handles LinkedIn OAuth + scheduling on our behalf; our agent just calls Buffer API |
| LLM | Anthropic Claude (Sonnet 4.6 default; Haiku 4.5 for cheap tasks like hashtags) | User already on Claude; high-quality long-form writing |
| Image | Unsplash API (free) | License-clear stock images, keyword search |
| State storage | SQLite committed to repo | Zero infra, version history via git, trivial to query |
| External sources | arXiv RSS, Hacker News API, Reddit JSON, GitHub API, Google Trends (free) | No paid APIs |

LinkedIn's official Marketing API is explicitly avoided for v1. Buffer abstracts the LinkedIn OAuth + posting concerns and removes the ToS / token-refresh / rate-limit complexity for a single-user personal-feed use case.

---

## 3. End-to-end flow

```
[GitHub Actions cron @ 08:00 ET]
   ↓ runs agent.draft
[Pick post type from 7-day rotation]
   ↓
[Fetch source content (profile / arXiv / HN / Reddit / GitHub)]
   ↓
[Claude → caption + hashtags]
   ↓
[Unsplash → image URL]
   ↓
[Save draft row in SQLite, status=pending, expires_at=+24h]
   ↓
[Sign approve/reject HMAC tokens]
   ↓
[Gmail SMTP → email Anuj w/ caption preview, image, APPROVE / REJECT buttons]
   ↓
[Commit SQLite back to repo (git push)]

[Anuj clicks APPROVE in email]
   ↓
[Cloudflare Worker /a?t=token]
   ↓ verify HMAC, extract draft_id
[Worker → GitHub API workflow_dispatch on post.yml]
   ↓
[Worker returns "✅ Posting…" page]

[GitHub Actions post.yml runs agent.post --draft-id=xxx]
   ↓
[Load draft from SQLite (idempotent: skip if not pending)]
   ↓
[Buffer API → schedule post for next 11:00 ET]
   ↓
[Update SQLite: status=posted, buffer_post_id]
   ↓
[Email Anuj confirmation]
   ↓
[Commit SQLite]

[Buffer publishes to LinkedIn @ 11:00 ET]
```

Reject path is identical but the Worker dispatches a reject action (or the same workflow with `--action=reject`); the draft is marked `rejected` and no Buffer call is made. Anuj receives a "skipped" confirmation email.

---

## 4. Repository layout

```
linkedin-agent/
├── master_profile.json              # source of truth for Anuj's profile
├── master_profile.example.json      # sanitized template
├── requirements.txt
├── README.md
├── pyproject.toml                   # ruff, mypy, pytest config
├── Makefile                         # smoke targets
├── db/
│   └── state.sqlite                 # committed to repo
├── src/agent/
│   ├── __init__.py
│   ├── draft.py                     # entrypoint: build + email draft
│   ├── post.py                      # entrypoint: send to Buffer
│   ├── rotation.py                  # pick post type for today
│   ├── config.py                    # env loading + constants
│   ├── sources/
│   │   ├── profile.py
│   │   ├── arxiv.py
│   │   ├── hn.py
│   │   ├── reddit.py
│   │   ├── github.py
│   │   └── trends.py
│   ├── generators/
│   │   ├── caption.py
│   │   ├── hashtags.py
│   │   └── image.py
│   ├── delivery/
│   │   ├── email.py
│   │   └── buffer.py
│   ├── auth/
│   │   └── tokens.py
│   └── db/
│       ├── schema.sql
│       └── store.py
├── worker/
│   ├── approval.js                  # Cloudflare Worker source
│   └── wrangler.toml
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── smoke/
│   └── fixtures/
└── .github/workflows/
    ├── draft.yml                    # cron 08:00 ET daily
    ├── post.yml                     # workflow_dispatch on approval
    └── test.yml                     # on push: lint + type + unit
```

---

## 5. Post types & rotation

| Day | Post type | Primary source | Description |
|---|---|---|---|
| Mon | Project breakdown | `profile.projects[]` (rotate) | "How I built X / what I learned" — pick next project, frame using `framings.data_scientist` (or rotate framing too) |
| Tue | Concept explainer | `profile.skills` → Claude pick | Quick explainer of an ML/SQL/stats concept Anuj actually uses |
| Wed | Tip / insight | `profile.experience[].bullets` | Concrete metric-driven lesson from Scaler / Unacademy / Vedantu work |
| Thu | Industry commentary | arXiv top ML paper this week | React to a fresh paper with Anuj's framing |
| Fri | Skill showcase | `profile.skills` category | "5 SQL window function tricks I use daily" style |
| Sat | Career / journey | `profile.education` + `profile.achievements` | OPT, MS, ASEE win, Mech Eng → DS pivot |
| Sun | Poll / question | HN/Reddit trending → frame as Q | Engagement bait tied to a real trending topic |

Rotation state is persisted in `rotation_state` table: `project_index`, `skill_index`, `exp_index` each cycle independently so projects don't repeat until the full cycle completes. `last_day` makes the cron idempotent: re-running on the same day exits without producing a second draft.

All posts include 5–8 hashtags. Hashtag mix is 60% evergreen (`#DataScience`, `#MachineLearning`) and 40% niche to the specific post (`#AttentionUNet`, `#SHAP`, `#OPTJobs`).

---

## 6. Component responsibilities

Each module has one job and is unit-testable in isolation.

| Module | Input | Output | Side effects |
|---|---|---|---|
| `rotation.pick_today()` | today's date, DB state | `(post_type, sub_key)` or `None` if already drafted | reads `rotation_state` |
| `rotation.advance(post_type)` | post_type | — | writes `rotation_state` |
| `sources.profile.fetch(post_type, sub_key, profile)` | post_type, profile dict | source dict: `{title, body, metrics, keywords, context}` | none |
| `sources.arxiv.fetch_top()` | — | source dict | network |
| `sources.hn.fetch_trending()` | — | source dict | network |
| `sources.reddit.fetch_top()` | — | source dict | network |
| `sources.github.fetch_recent_commits()` | — | source dict | network |
| `generators.caption.build(post_type, source, voice_profile)` | inputs | caption string (800–1300 chars) | Anthropic API call |
| `generators.hashtags.build(post_type, source, caption)` | inputs | list[str] of 5–8 hashtags | Anthropic API call (Haiku) |
| `generators.image.fetch(keywords)` | keywords | `(url, credit)` | Unsplash API |
| `delivery.email.send_draft(draft, approve_url, reject_url)` | draft + URLs | — | Gmail SMTP |
| `delivery.email.send_confirmation(draft, status)` | draft, status | — | Gmail SMTP |
| `delivery.buffer.schedule(text, image_url, when)` | text, image, datetime | `buffer_post_id` | Buffer API |
| `auth.tokens.sign(draft_id, action)` | draft_id, "approve"\|"reject" | signed token string | none |
| `auth.tokens.verify(token)` | token | `(draft_id, action)` or raises | none |
| `db.store.*` | varies | varies | SQLite read/write |
| `worker/approval.js` | HTTP GET w/ token | HTML response | calls GitHub API |

Boundaries between layers (sources / generators / delivery / db) keep external services swappable. For example, replacing Buffer with the official LinkedIn API later only touches `delivery/buffer.py`.

---

## 7. Database schema

```sql
CREATE TABLE drafts (
    id              TEXT PRIMARY KEY,           -- uuid4
    created_at      TEXT NOT NULL,              -- ISO8601 UTC
    post_type       TEXT NOT NULL,              -- project|concept|tip|commentary|skill|career|poll
    source_ref      TEXT,                       -- e.g. "project:afm" or arxiv URL
    caption         TEXT NOT NULL,
    hashtags        TEXT NOT NULL,              -- space-joined
    image_url       TEXT,
    image_credit    TEXT,
    status          TEXT NOT NULL,              -- pending|approved|rejected|posted|expired|error
    expires_at      TEXT NOT NULL,
    approved_at     TEXT,
    posted_at       TEXT,
    buffer_post_id  TEXT,
    error           TEXT
);

CREATE TABLE rotation_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_day        TEXT,
    project_index   INTEGER DEFAULT 0,
    skill_index     INTEGER DEFAULT 0,
    exp_index       INTEGER DEFAULT 0
);

CREATE TABLE post_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id        TEXT REFERENCES drafts(id),
    post_type       TEXT,
    source_ref      TEXT,
    posted_at       TEXT,
    linkedin_url    TEXT
);

CREATE TABLE source_seen (
    source          TEXT NOT NULL,              -- arxiv|hn|reddit|github
    ref             TEXT NOT NULL,
    seen_at         TEXT NOT NULL,
    PRIMARY KEY (source, ref)
);
```

Status transitions: `pending → approved → posted` (happy path), `pending → rejected`, `pending → expired` (24h timeout), or `* → error`.

Storing the DB in git gives a free audit log: `git log db/state.sqlite` shows every change. The DB is small (KB range) for the foreseeable future.

---

## 8. Approval token design

Token format: base64url of:

```
{draft_id}|{action}|{expires_unix_ts}|{hmac_sha256(secret, "draft_id|action|expires")}
```

- `HMAC_SECRET` is a 32-byte random value stored in GitHub Actions Secrets and the Cloudflare Worker secret env.
- Token carries its own expiry (24 hours from issue). Worker rejects on expiry mismatch or HMAC mismatch.
- The DB's `expires_at` provides a second layer of expiry, so even a leaked-but-not-expired token fails if the draft was already marked `expired` or `rejected`.
- Idempotency: a double-click on APPROVE leads to a no-op because `agent.post` checks `status == "pending"` before acting.

---

## 9. Cloudflare Worker

```
GET /a?t={token}   → approve action
GET /r?t={token}   → reject action
GET /              → healthcheck
```

Worker logic:

1. Verify HMAC + expiry (constant-time compare).
2. POST `https://api.github.com/repos/99anujb/linkedin-agent/actions/workflows/post.yml/dispatches` with body `{ref: "main", inputs: {draft_id, action}}` and `Authorization: Bearer GH_PAT`.
3. Return a small HTML page: "✅ Approved — Buffer will publish at 11:00 ET" or "❌ Rejected".

The PAT is scoped to `actions:write` on the single repo only.

---

## 10. GitHub Actions workflows

**`.github/workflows/draft.yml`** — cron `0 12 * * *` (12:00 UTC = 08:00 ET when DST is active; we'll handle the DST shift explicitly with two cron lines or a UTC offset that's "close enough" given the 3-hour gap before posting):

```yaml
on:
  schedule:
    - cron: '0 12 * * *'   # 08:00 ET (DST) / 07:00 ET (standard)
  workflow_dispatch:       # manual trigger for testing
jobs:
  draft:
    runs-on: ubuntu-latest
    permissions:
      contents: write        # to commit SQLite back
    steps:
      - checkout
      - setup python 3.11
      - pip install -r requirements.txt
      - python -m agent.draft
        env: { all secrets }
      - git config + commit + push db/state.sqlite if changed
```

**`.github/workflows/post.yml`** — `workflow_dispatch` with `inputs.draft_id` and `inputs.action`:

```yaml
on:
  workflow_dispatch:
    inputs:
      draft_id: { required: true }
      action:   { required: true }   # approve | reject
jobs:
  post:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - checkout
      - setup python
      - pip install -r requirements.txt
      - python -m agent.post --draft-id=${{ inputs.draft_id }} --action=${{ inputs.action }}
      - commit + push db/state.sqlite
```

**`.github/workflows/test.yml`** — on push: ruff, mypy, pytest (unit + integration).

---

## 11. Error handling

| Failure | Detection | Action |
|---|---|---|
| Anthropic API down / rate-limited | exception | retry 3× exponential backoff (1s → 4s → 16s); else email "draft failed" |
| Unsplash API down | exception | fall back to a pre-picked stock image per category |
| Source fetch fails (arXiv/HN/Reddit/GitHub) | exception | fall back to next source in chain; ultimately fall back to a profile-based post type |
| Gmail SMTP fails | exception | retry once; on final fail, write error to SQLite and fail the workflow (GitHub emails on workflow failure) |
| Buffer API fails | exception | retry 3×; on final fail, mark draft `error`, email "manual post needed" with full caption |
| Buffer quota exhausted | 4xx response | same as above |
| Worker → GitHub dispatch fails | non-200 from GitHub | Worker returns 500, user retries the link |
| Cron run skipped | next day's run sees `last_day != yesterday` | log warning + email |
| Duplicate cron run | `rotation_state.last_day == today` | exit cleanly, no double draft |
| Approval token tampered / expired | HMAC mismatch / expiry check | Worker returns 401 / 410 page |
| Approval double-click | `drafts.status != "pending"` | `agent.post` exits no-op |
| Profile JSON malformed | startup validation | fail fast, alert |
| SQLite corruption | open fails | restore from last known-good git commit, alert |

All network calls use `tenacity` for retry. The expiry sweep runs as the first step in `agent.draft`: any `pending` draft older than 24h is marked `expired` before a new one is created.

---

## 12. Observability

- Workflow run logs in GitHub Actions UI (retained 90 days).
- `drafts` and `post_history` tables are the audit trail. Queryable via `sqlite3 db/state.sqlite`.
- GitHub Actions emails on workflow failure (built-in, free).
- (Phase 4) Buffer analytics API → weekly digest email with engagement per post type to inform rotation weighting.

---

## 13. Manual override CLI

For debugging and one-off operations, all entrypoints are runnable locally:

```
python -m agent.draft --dry-run                    # generate, print, don't email or commit
python -m agent.draft --post-type=concept          # force a specific type
python -m agent.draft --force                      # ignore "already drafted today"
python -m agent.post --draft-id=<id> --action=approve
python -m agent.post --draft-id=<id> --action=reject
python -m agent.db list-pending
python -m agent.db expire <id>
python -m agent.rotation reset
```

---

## 14. Security

- All secrets live in GitHub Actions Secrets and Cloudflare Worker secret env. None in the repo.
- Required secrets:
  - `ANTHROPIC_API_KEY`
  - `GMAIL_APP_PASSWORD` (Gmail app password, not main pw)
  - `UNSPLASH_ACCESS_KEY`
  - `BUFFER_ACCESS_TOKEN`
  - `BUFFER_LINKEDIN_PROFILE_ID`
  - `HMAC_SECRET` (32 random bytes)
  - `GH_PAT_FOR_DISPATCH` (fine-grained PAT: `actions:write` on this repo only)
- The GitHub repository **must be private**: `master_profile.json` contains PII (phone, email).
- Gmail must have 2FA enabled; we use an app password rather than the main password.
- The Cloudflare Worker validates HMAC in constant time to prevent timing attacks.

---

## 15. Testing strategy

**Unit tests** for pure logic: rotation mapping & cycling, HMAC sign/verify, prompt construction, hashtag rules, DB CRUD, email template rendering, request body shapes.

**Integration tests** with mocked HTTP (using `respx`): full `agent.draft` pipeline, full `agent.post` pipeline, Worker handler (via `vitest` + `miniflare`).

**Smoke tests** (manual, not in CI): one live call per external service before deploy.

**Dry-run end-to-end**: `python -m agent.draft --dry-run` runs the full pipeline against real APIs but prints the email instead of sending — used weekly to detect silent breakage.

CI runs lint + types + unit + integration on every push. Smoke tests run via `make smoke-*` targets locally.

---

## 16. Phasing

**Phase 1 — MVP, no LinkedIn integration yet**

- Profile-only sources (skip arXiv / HN / Reddit / GitHub).
- 3 post types: project, concept, tip.
- Email-only delivery: Anuj copy-pastes manually to LinkedIn at 11:00 ET.
- Cron + draft + email + approval link (the link just marks the DB; no Buffer call yet).
- Validates: prompt quality, voice, rotation.

**Phase 2 — Buffer integration**

- `delivery/buffer.py` + Cloudflare Worker approval handler.
- True auto-scheduling at 11:00 ET.

**Phase 3 — Remaining post types + external sources**

- Career, commentary, skill showcase, poll.
- arXiv, HN, Reddit, GitHub sources.

**Phase 4 — Engagement feedback loop**

- Buffer analytics → weekly digest.
- Auto-tune rotation weighting toward post types that perform best.

---

## 17. Anuj's setup checklist

Before implementation begins:

- [ ] Create a private GitHub repository (e.g., `linkedin-agent`).
- [ ] Anthropic API key (already have, via Claude Code).
- [ ] Gmail app password (`myaccount.google.com` → 2-Step Verification → App passwords).
- [ ] Unsplash developer account → access key (`unsplash.com/developers`).
- [ ] Buffer account on free plan → connect LinkedIn profile → generate API token (`publish.buffer.com` → Apps & Extras → Access Tokens).
- [ ] Cloudflare account (free) for the Worker.
- [ ] Generate a 32-byte HMAC secret (`openssl rand -base64 32`).
- [ ] Fine-grained GitHub PAT scoped `actions:write` on the new repo.

---

## 18. Open questions / decisions deferred

- Daylight-saving handling: a single UTC cron drifts by an hour twice a year. Phase 1 will live with the drift (draft generated at 07:00 or 08:00 ET, post still scheduled relative to local 11:00 ET via Buffer). Revisit in Phase 2 if it becomes annoying.
- Whether to support multi-image carousels (Buffer free tier may not). Defer until Phase 3.
- Whether to allow inline edits from the email (reply with edited text, IMAP polled). Defer; for v1 REJECT and wait for tomorrow is fine.
