// Cloudflare Worker: receives APPROVE/REJECT clicks from draft email,
// verifies HMAC token, dispatches the GitHub Actions `post.yml` workflow.
//
// Required environment (set via `wrangler secret put`):
//   - HMAC_SECRET            (same value as the Python agent's HMAC_SECRET)
//   - GH_PAT                 (fine-grained PAT with `actions:write` on the repo)
//   - GH_REPO                ("owner/name", e.g. "99anujb/linkedin-agent")
//   - GH_WORKFLOW_FILE       ("post.yml")
//   - GH_REF                 (branch to dispatch on, e.g. "main")

const VALID_ACTIONS = new Set(["approve", "reject"]);

function b64urlDecodeToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4;
  if (pad) s += "=".repeat(4 - pad);
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function verifyToken(token, secret) {
  const dot = token.indexOf(".");
  if (dot < 1) throw new Error("malformed token");
  const payloadB64 = token.slice(0, dot);
  const sigB64 = token.slice(dot + 1);

  const payloadBytes = b64urlDecodeToBytes(payloadB64);
  const sigBytes = b64urlDecodeToBytes(sigB64);

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
  const ok = await crypto.subtle.verify("HMAC", key, sigBytes, payloadBytes);
  if (!ok) throw new Error("bad signature");

  const text = new TextDecoder().decode(payloadBytes);
  const parts = text.split("|");
  if (parts.length !== 3) throw new Error("malformed payload");
  const [draftId, action, expiresStr] = parts;
  if (!VALID_ACTIONS.has(action)) throw new Error("bad action");
  const expires = parseInt(expiresStr, 10);
  if (!Number.isFinite(expires)) throw new Error("bad expiry");
  if (Math.floor(Date.now() / 1000) > expires) throw new Error("token expired");
  return { draftId, action };
}

async function dispatchWorkflow(env, draftId, action) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${env.GH_WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_PAT}`,
      "User-Agent": "linkedin-agent-approval-worker",
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: env.GH_REF,
      inputs: { draft_id: draftId, action },
    }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`github dispatch failed: ${resp.status} ${body}`);
  }
}

function htmlPage(title, body, color = "#0a66c2") {
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title></head>
     <body style="font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f7f7f9">
       <div style="max-width:480px;padding:32px;background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
         <h2 style="color:${color};margin-top:0">${title}</h2>
         <p style="color:#444">${body}</p>
       </div>
     </body></html>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }
    const expectedAction =
      url.pathname === "/a" ? "approve"
      : url.pathname === "/r" ? "reject"
      : null;
    if (expectedAction === null) return new Response("not found", { status: 404 });

    const token = url.searchParams.get("t");
    if (!token) return htmlPage("Missing token", "No token provided.", "#b91c1c");

    let payload;
    try {
      payload = await verifyToken(token, env.HMAC_SECRET);
    } catch (e) {
      const msg = String(e.message || e);
      const status = msg.includes("expired") ? "Token expired" : "Invalid token";
      return htmlPage(status, "This approval link is no longer valid.", "#b91c1c");
    }

    if (payload.action !== expectedAction) {
      return htmlPage("Action mismatch", "The token does not match this URL.", "#b91c1c");
    }

    try {
      await dispatchWorkflow(env, payload.draftId, payload.action);
    } catch (e) {
      return htmlPage("Dispatch failed", String(e.message || e), "#b91c1c");
    }

    const verb = payload.action === "approve" ? "approved" : "rejected";
    return htmlPage(
      `Draft ${verb}`,
      payload.action === "approve"
        ? "Buffer will publish at the configured local time."
        : "Draft skipped. The cron will draft a new one tomorrow.",
      payload.action === "approve" ? "#0a66c2" : "#6b7280",
    );
  },
};
