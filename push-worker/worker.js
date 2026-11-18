// A2O SOUL Tracker — Cloudflare Worker
//  1) 웹 푸시 구독 저장 (사이트 '🔔 알림')
//  2) 10분마다 GitHub Actions 수집 실행 (Cron Trigger: */10 * * * *)
//  3) YouTube 새 영상 즉시 알림(WebSub) 받으면 바로 수집 실행
// 설정: KV 바인딩 SUBS / 변수 VAPID_PUBLIC (VAPID 공개키) / 비밀(Secret) GH_TOKEN (Actions 실행 권한만 있는 GitHub 토큰)
//       비밀(Secret) CHART_KEY — 차트 순위 입력 비밀번호 (총공팀 차트 담당과만 공유)
//
// 엔드포인트
//   POST /subscribe   {sub, topics, lang}   — 사이트에서 구독/설정 변경
//   POST /unsubscribe {endpoint}            — 사이트에서 구독 해제
//   GET  /subs                               — 발송용 목록 (GitHub Actions만: VAPID 비밀키 서명 토큰)
//   POST /prune       {ids}                  — 만료된 구독 삭제 (GitHub Actions만)
//   GET/POST /yt-hook                        — YouTube WebSub 콜백
//   GET  /yt-renew                           — YouTube 알림 구독 지금 갱신 (평소엔 하루 한 번 자동)
//   POST /chart  {key, song, service, rank}  — 차트 순위 입력 (사이트 chart.html, 비밀 CHART_KEY) → 바로 수집 실행(알림)
//   GET  /charts                             — 입력된 순위 목록 (수집용, 공개)
const REPO = "han-gaeul/a2o-soul-dashboard";
const WORKFLOW = "update.yml";
const SITE = "https://a2osoul-tracker.com";
const HOOK = "https://push.a2osoul-tracker.com/yt-hook";
const ORIGINS = [SITE, "http://localhost:8765"];
const TOPICS = ["notice", "vote", "show", "video", "birthday"];
const LANGS = ["ko", "en", "ja", "zh", "es", "id", "th", "pt"];
const GROUP = /A2O\s?SOUL|A2OSOUL|에이투오\s?소울/i;
const OWN_CHANNELS = ["UCAdLPETtxpZeRVqsq_QTneA", "UCn-SYb1TUz-1itK_uz4imUA"]; // A2O SOUL, A2O WORLD — 제목 상관없이 실행

const enc = new TextEncoder();
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const idOf = async (endpoint) => hex(await crypto.subtle.digest("SHA-256", enc.encode(endpoint))).slice(0, 32);
const hubSecret = async (env) => hex(await crypto.subtle.digest("SHA-256", enc.encode("websub:" + (env.GH_TOKEN || "")))).slice(0, 40);

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
    const ok = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, b64u(m[3]), enc.encode(`${m[1]}.${m[2]}`));
    const claims = JSON.parse(new TextDecoder().decode(b64u(m[2])));
    return ok && claims.aud === "push-admin" && claims.exp > Date.now() / 1000 && claims.exp < Date.now() / 1000 + 900;
  } catch (_) {
    return false;
  }
}

// GitHub Actions 수집 실행 (같은 실행이 줄 서 있으면 GitHub가 하나로 합쳐 줌)
async function dispatch(env, why) {
  if (!env.GH_TOKEN) return console.log("GH_TOKEN 없음");
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "a2o-push-worker",
      "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }),
  });
  console.log(`수집 실행 (${why}): ${r.status}`);
  return r.status;
}

// YouTube 채널 새 영상 알림 구독 (5일마다 만료 → 하루 한 번 갱신). 채널 목록은 사이트 데이터에서
async function renewYoutube(env) {
  let ids = [];
  try {
    ids = (await (await fetch(`${SITE}/data/dashboard.json`, { cf: { cacheTtl: 300 } })).json()).yt_channels || [];
  } catch (_) { /* 무시 */ }
  const secret = await hubSecret(env);
  const out = [];
  for (const id of ids) {
    const body = new URLSearchParams({ "hub.callback": HOOK, "hub.mode": "subscribe", "hub.verify": "async", "hub.lease_seconds": "432000",
      "hub.topic": `https://www.youtube.com/xml/feeds/videos.xml?channel_id=${id}`, "hub.secret": secret });
    const r = await fetch("https://pubsubhubbub.appspot.com/subscribe", { method: "POST", body });
    out.push(`${id}:${r.status}`);
  }
  console.log("YouTube 알림 구독:", out.join(" "));
  return out;
}

async function youtubeHook(req, env) {
  const url = new URL(req.url);
  if (req.method === "GET") { // 구독 확인: 우리 채널 피드만 수락
    const topic = url.searchParams.get("hub.topic") || "";
    const ok = /^https:\/\/www\.youtube\.com\/xml\/feeds\/videos\.xml\?channel_id=UC[\w-]{22}$/.test(topic);
    return new Response(ok ? url.searchParams.get("hub.challenge") || "" : "no", { status: ok ? 200 : 404 });
  }
  const body = await req.text();
  const sig = (req.headers.get("X-Hub-Signature") || "").replace(/^sha1=/, "");
  const key = await crypto.subtle.importKey("raw", enc.encode(await hubSecret(env)), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  if (hex(await crypto.subtle.sign("HMAC", key, enc.encode(body))) !== sig) return new Response("bad signature", { status: 403 });
  const title = (body.match(/<entry>[\s\S]*?<title>([^<]*)<\/title>/) || [])[1] || "";
  const channel = (body.match(/<yt:channelId>([^<]+)<\/yt:channelId>/) || [])[1] || "";
  const deleted = body.includes("at:deleted-entry");
  if (!deleted && (OWN_CHANNELS.includes(channel) || GROUP.test(title))) {
    // 같은 영상 알림이 여러 번 와도 2분에 한 번만 실행
    const last = Number(await env.SUBS.get("_dispatch_at")) || 0;
    if (Date.now() - last > 120000) {
      await env.SUBS.put("_dispatch_at", String(Date.now()), { expirationTtl: 3600 });
      await dispatch(env, `YouTube 새 영상: ${title.slice(0, 60)}`);
    }
  }
  return new Response("ok");
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });

    if (url.pathname === "/yt-hook") return youtubeHook(req, env);
    if (req.method === "GET" && url.pathname === "/yt-renew") { // 10분에 한 번만
      if (Date.now() - (Number(await env.SUBS.get("_renew_at")) || 0) < 600000) return json(req, { ok: true, skipped: "10분 안에 이미 갱신" });
      await env.SUBS.put("_renew_at", String(Date.now()), { expirationTtl: 3600 });
      return json(req, { ok: true, subscribed: await renewYoutube(env) });
    }

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

    if (req.method === "POST" && url.pathname === "/chart") {
      const b = await req.json().catch(() => ({}));
      const keyOk = env.CHART_KEY && typeof b.key === "string" && b.key.length === env.CHART_KEY.length
        && hex(await crypto.subtle.digest("SHA-256", enc.encode(b.key))) === hex(await crypto.subtle.digest("SHA-256", enc.encode(env.CHART_KEY)));
      if (!keyOk) return json(req, { error: "비밀번호가 달라요" }, 403);
      const song = String(b.song || "").slice(0, 60).trim(), service = String(b.service || "").slice(0, 30).trim();
      const rank = b.rank === null ? null : Number(b.rank);
      if (!song || !service || !(rank === null || (Number.isInteger(rank) && rank >= 1 && rank <= 300))) return json(req, { error: "곡·차트·순위를 확인해 주세요" }, 400);
      const at = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16).replace("T", " "); // KST
      const list = (await env.SUBS.get("_charts", "json")) || [];
      list.push({ song, service, rank, at });
      await env.SUBS.put("_charts", JSON.stringify(list.slice(-2000)));
      // 바로 수집 실행 → 알림 (2분에 한 번만)
      if (Date.now() - (Number(await env.SUBS.get("_chart_dispatch")) || 0) > 120000) {
        await env.SUBS.put("_chart_dispatch", String(Date.now()), { expirationTtl: 3600 });
        await dispatch(env, "차트 입력");
      }
      return json(req, { ok: true, at });
    }
    if (req.method === "GET" && url.pathname === "/charts") {
      return json(req, (await env.SUBS.get("_charts", "json")) || []);
    }

    if (req.method === "GET" && url.pathname === "/subs") {
      if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
      const out = [];
      let cursor;
      do {
        const page = await env.SUBS.list({ cursor });
        for (const k of page.keys) {
          if (k.name.startsWith("_")) continue; // 내부용 키
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

  // Cron Trigger (*/10 * * * *): 10분마다 수집 실행, 하루 한 번(KST 12시대) YouTube 알림 구독 갱신
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, "10분 정기"));
    const t = new Date(event.scheduledTime);
    if (t.getUTCHours() === 3 && t.getUTCMinutes() < 10) ctx.waitUntil(renewYoutube(env));
  },
};
