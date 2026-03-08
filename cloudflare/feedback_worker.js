// Cloudflare Worker for web feedback viewer and feedback capture.
// Routes:
// - GET /run?run_id=<run_id>
// - GET /feedback?t=<signed_token>
// Env bindings:
// - DB (D1 database)
// - FEEDBACK_LINK_SIGNING_SECRET (secret text)

function b64urlToBytes(s) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const base64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(base64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function verifyToken(token, secret) {
  if (!token || !token.includes(".")) throw new Error("invalid token format");
  const [payloadB64, sigB64] = token.split(".", 2);
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const expected = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(payloadB64)));
  const got = b64urlToBytes(sigB64);
  if (bytesToHex(expected) !== bytesToHex(got)) throw new Error("invalid signature");

  const payloadJson = new TextDecoder().decode(b64urlToBytes(payloadB64));
  const claims = JSON.parse(payloadJson);
  if (!claims || !claims.exp) throw new Error("invalid claims");
  if (new Date(claims.exp).getTime() < Date.now()) throw new Error("token expired");
  if (!["positive", "negative", "undecided"].includes(String(claims.label || "").toLowerCase())) {
    throw new Error("invalid label");
  }
  if (!String(claims.run_id || "").trim() || !String(claims.item_id || "").trim()) {
    throw new Error("missing run_id/item_id");
  }
  return claims;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/run") {
      const runId = String(url.searchParams.get("run_id") || "").trim();
      if (!runId) {
        return new Response("Missing run_id", { status: 400 });
      }
      const row = await env.DB
        .prepare(`SELECT report_html, created_at FROM feedback_runs WHERE run_id = ? LIMIT 1`)
        .bind(runId)
        .first();
      if (!row || !row.report_html) {
        return new Response("Run not found", { status: 404 });
      }
      const html = `<!doctype html>
<html><head><meta charset="utf-8"><title>Paper Digest Feedback</title></head>
<body>
  <div style="margin:12px 0;padding:10px;border:1px solid #d0dae6;border-radius:10px;background:#f8fbff;">
    <strong>Paper Digest Feedback Viewer</strong><br/>
    run_id: <code>${runId}</code>
  </div>
  ${row.report_html}
</body></html>`;
      return new Response(html, {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    if (url.pathname === "/feedback") {
      const token = url.searchParams.get("t") || "";
      try {
        const claims = await verifyToken(token, env.FEEDBACK_LINK_SIGNING_SECRET);
        const eventId = `evt_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
        const createdAt = new Date().toISOString();
        await env.DB
          .prepare(
            `INSERT INTO feedback_events
             (event_id, run_id, item_id, label, reviewer, created_at, source, status, resolved_semantic_paper_id, applied_at, error)
             VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)`
          )
          .bind(
            eventId,
            String(claims.run_id || ""),
            String(claims.item_id || ""),
            String(claims.label || "").toLowerCase(),
            String(claims.reviewer || ""),
            createdAt,
            "web_viewer",
            String(claims.semantic_paper_id || "") || null
          )
          .run();
        const backUrl = `/run?run_id=${encodeURIComponent(String(claims.run_id || ""))}`;
        return new Response(
          `<!doctype html><html><body><p>Feedback recorded: ${claims.label} (${claims.item_id})</p><p><a href="${backUrl}">Back to report viewer</a></p></body></html>`,
          { status: 200, headers: { "content-type": "text/html; charset=utf-8" } }
        );
      } catch (err) {
        return new Response(`Feedback rejected: ${err.message}`, { status: 400 });
      }
    }
    return new Response("Not Found", { status: 404 });
  },
};
