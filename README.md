# LinkedIn Auto-Post Agent — Phase 1

Daily LinkedIn draft emailed to you for manual posting. See
`docs/superpowers/specs/2026-05-13-linkedin-auto-post-agent-design.md`
for the full design.

## Setup (local dev)

```
make install
cp .env.example .env
# fill in ANTHROPIC_API_KEY, UNSPLASH_ACCESS_KEY, GMAIL_APP_PASSWORD
python -m agent draft --dry-run
```

## Setup (GitHub Actions)

1. Create a private repo and push this code.
2. Add these Repository Secrets:
   - `ANTHROPIC_API_KEY`
   - `UNSPLASH_ACCESS_KEY`
   - `GMAIL_USERNAME`
   - `GMAIL_APP_PASSWORD`
   - `GMAIL_RECIPIENT`
   - `PROFILE_B64` — base64 of `master_profile.json`
     (`base64 -i master_profile.json | pbcopy`)
3. Cron runs daily at 12:00 UTC (≈ 08:00 ET). You receive an email
   draft and post it manually at 11:00 ET.

## CLI

```
python -m agent draft --dry-run         # generate, print, no email or commit
python -m agent draft --post-type=tip   # force a post type
python -m agent draft --force           # ignore "already drafted today"
python -m agent db list-pending         # show pending drafts
```

## Deploy to GitHub Actions

1. Create a **private** GitHub repo (e.g. `linkedin-agent`). Push this code:

   ```
   git remote add origin git@github.com:<your-user>/linkedin-agent.git
   git push -u origin main
   ```

2. Generate a Gmail app password:
   `myaccount.google.com` → Security → 2-Step Verification → App passwords →
   create one for "Mail" → copy the 16-character password.

3. Get an Unsplash access key at `unsplash.com/developers` → New Application →
   copy the **Access Key** (not the Secret).

4. Base64-encode your real `master_profile.json` (do **not** commit it):

   ```
   base64 -i master_profile.json | tr -d '\n' | pbcopy
   ```

5. In the GitHub repo → Settings → Secrets and variables → Actions, add:
   - `ANTHROPIC_API_KEY`
   - `UNSPLASH_ACCESS_KEY`
   - `GMAIL_USERNAME` (e.g. `99anujbansal@gmail.com`)
   - `GMAIL_APP_PASSWORD` (the 16-character app password)
   - `GMAIL_RECIPIENT` (usually same as username)
   - `PROFILE_B64` (paste the base64 from step 4)

6. Trigger a manual run to verify everything wires up:
   Actions → "draft" → Run workflow → Run.

7. Watch the run; check your inbox for the draft email.

8. Once a manual run succeeds, the daily cron will fire automatically at
   12:00 UTC (≈ 08:00 ET).

## Phase 2: Buffer + Cloudflare Worker

Phase 2 adds APPROVE / REJECT buttons in the draft email. Clicking a button
hits a Cloudflare Worker that triggers a `post.yml` GitHub Actions workflow,
which schedules the post on Buffer for 11:00 ET.

### One-time setup

1. **Buffer.** Create a free Buffer account, connect your LinkedIn profile,
   then create an API access token at
   `https://publish.buffer.com/developers/apps`.

2. **Discover your Buffer LinkedIn profile id.** Locally:

   ```
   python -m scripts.discover_buffer_profile
   ```

   Copy the `id` for the `linkedin` row into `.env` as
   `BUFFER_LINKEDIN_PROFILE_ID`.

3. **HMAC secret.** Generate a 32-byte secret:

   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Put it in `.env` as `HMAC_SECRET`. (Mirror to GitHub and Cloudflare next.)

4. **Fine-grained GitHub PAT.** Create at
   `https://github.com/settings/personal-access-tokens/new`:
   - Resource owner: your account
   - Repository access: only `linkedin-agent`
   - Permissions: Actions = Read and write
   Copy the token; needed for Cloudflare.

5. **Deploy the Worker.** See `worker/README.md`.

   After deploy, copy the printed URL (e.g.
   `https://linkedin-agent-approval.<your-name>.workers.dev`) into `.env` as
   `APPROVAL_BASE_URL`.

6. **Mirror Phase 2 secrets to GitHub** (so `post.yml` can read them):

   - `BUFFER_ACCESS_TOKEN`
   - `BUFFER_LINKEDIN_PROFILE_ID`
   - `HMAC_SECRET`
   - `APPROVAL_BASE_URL`

   ```
   gh secret set BUFFER_ACCESS_TOKEN --repo 99anujb/linkedin-agent
   gh secret set BUFFER_LINKEDIN_PROFILE_ID --repo 99anujb/linkedin-agent
   gh secret set HMAC_SECRET --repo 99anujb/linkedin-agent
   gh secret set APPROVAL_BASE_URL --repo 99anujb/linkedin-agent
   ```

### End-to-end test

1. Trigger a fresh draft from Actions (or wait for the cron).
2. Open the draft email; verify it now shows APPROVE and REJECT buttons.
3. Click APPROVE; the Worker should redirect to a success page.
4. Check `https://github.com/99anujb/linkedin-agent/actions` — `post.yml` is running.
5. After the workflow succeeds, log in to Buffer; the post should appear in
   the Queue scheduled for the next 11:00 ET slot.
6. Wait until the scheduled time and verify the post lands on LinkedIn.
