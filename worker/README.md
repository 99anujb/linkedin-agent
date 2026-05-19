# Approval Worker

Cloudflare Worker that receives approve/reject clicks from the draft email
and dispatches the `post.yml` GitHub Actions workflow.

## One-time setup

1. Install Node 20+ if you don't have it.
2. Install wrangler:

   ```
   cd worker
   npm install
   ```

3. Log in to Cloudflare:

   ```
   npx wrangler login
   ```

4. Set secrets (you'll be prompted for each value):

   ```
   npx wrangler secret put HMAC_SECRET
   npx wrangler secret put GH_PAT
   npx wrangler secret put GH_REPO
   npx wrangler secret put GH_WORKFLOW_FILE
   npx wrangler secret put GH_REF
   ```

5. Deploy:

   ```
   npx wrangler deploy
   ```

   wrangler prints the deployed URL, e.g.
   `https://linkedin-agent-approval.<your-name>.workers.dev`.
   Set that as `APPROVAL_BASE_URL` in `.env` and as a repo secret.

## Smoke test

```
curl https://linkedin-agent-approval.<your-name>.workers.dev/health
# OK
```
