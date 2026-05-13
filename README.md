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
