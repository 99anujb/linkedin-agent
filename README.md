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
