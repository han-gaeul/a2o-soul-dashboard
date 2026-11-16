// A2O SOUL Tracker — 웹 푸시 구독 저장용 Cloudflare Worker
// 바인딩: KV 네임스페이스 → 변수 이름 SUBS / 변수(Variables): VAPID_PUBLIC = VAPID 공개키(base64url)
// 엔드포인트
//   POST /subscribe   {sub, topics, lang}   — 사이트에서 구독/설정 변경
//   POST /unsubscribe {endpoint}            — 사이트에서 구독 해제
//   GET  /subs                               — 발송용 목록 (GitHub Actions만: VAPID 비밀키로 서명한 토큰 필요)
//   POST /prune       {ids}                  — 만료된 구독 삭제 (GitHub Actions만)
const ORIGINS = ["https://a2osoul-tracker.com", "http://localhost:8765"];
const TOPICS = ["notice", "vote", "show", "video"];
const LANGS = ["ko", "en", "ja", "zh", "es", "id", "th", "pt"];

const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const idOf = async (endpoint) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint))).slice(0, 32);

function cors(req) {
  const o = req.headers.get("Origin");
  return {
    "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0],
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Vary": "Origin",
  };
}
const json = (req, body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

// GitHub Actions가 VAPID 비밀키로 서명한 ES256 토큰 확인 (공유 비밀번호 없이)
async function isAdmin(req, env) {
  const m = (req.headers.get("Authorization") || "").match(/^Bearer ([\w-]+)\.([\w-]+)\.([\w-]+)$/);
  if (!m || !env.VAPID_PUBLIC) return false;
  try {
    const key = await crypto.subtle.importKey("raw", b64u(env.VAPID_PUBLIC), { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
    const ok = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, b64u(m[3]), new TextEncoder().encode(`${m[1]}.${m[2]}`));
    const claims = JSON.parse(new TextDecoder().decode(b64u(m[2])));
    return ok && claims.aud === "push-admin" && claims.exp > Date.now() / 1000 && claims.exp < Date.now() / 1000 + 900;
  } catch (_) {
    return false;
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });

    if (req.method === "POST" && url.pathname === "/subscribe") {
      const body = await req.json().catch(() => null);
      const sub = body && body.sub;
      if (!sub || typeof sub.endpoint !== "string" || !sub.endpoint.startsWith("https://") || sub.endpoint.length > 1000
          || !sub.keys || typeof sub.keys.p256dh !== "string" || typeof sub.keys.auth !== "string") {
        return json(req, { error: "bad subscription" }, 400);
      }
      const topics = (Array.isArray(body.topics) ? body.topics : TOPICS).filter((t) => TOPICS.includes(t));
      const lang = LANGS.includes(body.lang) ? body.lang : "en";
      const id = await idOf(sub.endpoint);
      await env.SUBS.put(id, JSON.stringify({ sub: { endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth } }, topics, lang, at: Date.now() }));
      return json(req, { ok: true, id });
    }

    if (req.method === "POST" && url.pathname === "/unsubscribe") {
      const body = await req.json().catch(() => null);
      if (body && typeof body.endpoint === "string") await env.SUBS.delete(await idOf(body.endpoint));
      return json(req, { ok: true });
    }

    if (req.method === "GET" && url.pathname === "/subs") {
      if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
      const out = [];
      let cursor;
      do {
        const page = await env.SUBS.list({ cursor });
        for (const k of page.keys) {
          const v = await env.SUBS.get(k.name, "json");
          if (v) out.push({ id: k.name, ...v });
        }
        cursor = page.list_complete ? null : page.cursor;
      } while (cursor);
      return json(req, out);
    }

    if (req.method === "POST" && url.pathname === "/prune") {
      if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
      const body = await req.json().catch(() => ({}));
      for (const id of (body.ids || []).slice(0, 500)) if (/^[0-9a-f]{32}$/.test(id)) await env.SUBS.delete(id);
      return json(req, { ok: true });
    }

    return json(req, { ok: true, service: "a2o-soul-push" });
  },
};
