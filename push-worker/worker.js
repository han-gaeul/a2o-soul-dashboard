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
//   /board/*                                 — 커뮤니티 게시판 (아래 '커뮤니티 게시판' 참고, D1 바인딩 DB 필요)
//   GET  /charts                             — 입력된 순위 목록 (수집용, 공개)
const REPO = "han-gaeul/a2o-soul-dashboard";
const WORKFLOW = "update.yml";
const SITE = "https://a2osoul-tracker.com";
const HOOK = "https://push.a2osoul-tracker.com/yt-hook";
const ORIGINS = [SITE, "http://localhost:8765"];
const TOPICS = ["notice", "vote", "show", "video", "birthday"];
const LANGS = ["ko", "en", "ja", "zh", "es", "id", "th", "pt", "fil", "vi"];
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
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Device",
    "Vary": "Origin",
  };
}
// KV 무료 한도(읽기 하루 10만) 아끼기: 사이트 방문마다 읽던 차트 입력 목록은 엣지 캐시에 5분 보관
const CHART_CACHE = "https://push.a2osoul-tracker.com/_cache/charts";
async function chartsBody(env) {
  const hit = await caches.default.match(CHART_CACHE);
  if (hit) return hit.text();
  const body = (await env.SUBS.get("_charts")) || "[]";
  await caches.default.put(CHART_CACHE, new Response(body, { headers: { "Cache-Control": "public, max-age=300" } }));
  return body;
}
// 구독 정보를 키 메타데이터(1KB까지)에도 넣어 두면 /subs에서 목록만 읽고 끝 (구독자 수만큼 읽기 안 함)
function subMeta(v) {
  const m = { e: v.sub.endpoint, p: v.sub.keys.p256dh, a: v.sub.keys.auth, t: v.topics, l: v.lang, at: v.at };
  return JSON.stringify(m).length <= 1000 ? m : undefined;
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
async function dispatch(env, why, workflow = WORKFLOW) {
  if (!env.GH_TOKEN) return console.log("GH_TOKEN 없음");
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "a2o-push-worker",
      "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }),
  });
  console.log(`${workflow} 실행 (${why}): ${r.status}`);
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

// ---------- 커뮤니티 게시판 (D1 바인딩 DB) ----------
// 게시판: qna(질문·정보, 익명 가능) / trade(포카 교환, 구글 로그인만 — 익명은 목록도 안 보임)
// 익명은 닉네임+비밀번호. 신원: 구글 sub 해시 / 기기 ID 해시 (IP는 쓰지 않음, 화면엔 안 보임)
// 익명 글·댓글·신고는 Cloudflare Turnstile(사람 확인)을 통과해야 함 → 매크로 도배 방지
// 신고: 서로 다른 사람(계정·기기) 3명 → 글 숨김 + 쓴 사람(계정·기기) 30일 차단 (관리자가 풀 수 있음)
// 설정: D1 바인딩 DB / 변수 GOOGLE_CLIENT_ID / 비밀 ADMIN_EMAILS(쉼표로) / 비밀 BOARD_SALT(아무 긴 문자열) / 비밀 TURNSTILE_SECRET
const BOARDS = { qna: { cats: ["질문", "정보", "후기", "사담"], anon: true }, trade: { cats: ["구해요", "드려요", "교환해요"], anon: false } };
const LIMIT = { anon: 5, user: 20 };
const BAN_DAYS = 30;
const PRIVATE = /(01[016789][-\s.]?\d{3,4}[-\s.]?\d{4})|(\d{2,6}[-\s]\d{2,6}[-\s]\d{2,8})|(카톡|카카오톡|오픈채팅|텔레|telegram|라인\s?아이디|line\s?id)\s*[:：]?\s*\S+|(계좌|입금|송금)/i;
const LINK = /https?:\/\/|www\.|\.(com|net|kr|io|me|ly)\b/i;

async function schema(env) {
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, board TEXT, cat TEXT, member TEXT, title TEXT, body TEXT, nick TEXT,
      pw TEXT, uid TEXT, ip TEXT, dev TEXT, img INTEGER DEFAULT 0, pinned INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0, reports INTEGER DEFAULT 0,
      comments INTEGER DEFAULT 0, at INTEGER, edited INTEGER)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post INTEGER, body TEXT, nick TEXT, pw TEXT, uid TEXT, ip TEXT, dev TEXT,
      hidden INTEGER DEFAULT 0, reports INTEGER DEFAULT 0, at INTEGER)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS images (post INTEGER PRIMARY KEY, type TEXT, data BLOB)`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS reports (kind TEXT, target INTEGER, who TEXT, at INTEGER, PRIMARY KEY (kind, target, who))`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS bans (key TEXT PRIMARY KEY, until INTEGER, why TEXT)`),
    env.DB.prepare(`CREATE INDEX IF NOT EXISTS posts_board ON posts (board, pinned, id)`),
  ]);
}
const sha = async (s) => hex(await crypto.subtle.digest("SHA-256", enc.encode(s))).slice(0, 24);

// 요청한 사람: 구글 로그인(ID 토큰 확인) 또는 익명 + IP·기기 해시
async function who(req, env) {
  const salt = env.BOARD_SALT || "a2o";
  const dev = await sha(salt + "dev:" + (req.headers.get("X-Device") || "").slice(0, 64));
  const m = (req.headers.get("Authorization") || "").match(/^Bearer (.+)$/);
  let uid = null, admin = false;
  if (m && env.GOOGLE_CLIENT_ID) {
    const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(m[1])}`);
    if (r.ok) {
      const t = await r.json();
      if (t.aud === env.GOOGLE_CLIENT_ID && Number(t.exp) * 1000 > Date.now() && t.email_verified !== "false") {
        uid = await sha(salt + "g:" + t.sub);
        admin = (env.ADMIN_EMAILS || "").split(",").map((x) => x.trim().toLowerCase()).includes(String(t.email || "").toLowerCase());
      }
    }
  }
  const keys = [uid && `u:${uid}`, `d:${dev}`].filter(Boolean);
  const ban = await env.DB.prepare(`SELECT until FROM bans WHERE key IN (${keys.map(() => "?").join(",")}) AND until > ? ORDER BY until DESC LIMIT 1`)
    .bind(...keys, Date.now()).first();
  return { uid, dev, admin, banned: ban ? ban.until : 0, keys };
}
const pwHash = (env, pw) => sha((env.BOARD_SALT || "a2o") + "pw:" + pw);
const clean = (s, n) => String(s || "").replace(/[\u0000-\u0008\u000b-\u001f]/g, "").trim().slice(0, n);
const pub = (p) => ({ id: p.id, board: p.board, cat: p.cat, member: p.member, title: p.title, nick: p.nick, login: !!p.uid,
  img: !!p.img, pinned: !!p.pinned, hidden: !!p.hidden, comments: p.comments, at: p.at, edited: p.edited });

async function banAuthor(env, row, why) {
  const until = Date.now() + BAN_DAYS * 864e5;
  const keys = [row.uid && `u:${row.uid}`, row.dev && `d:${row.dev}`].filter(Boolean);
  await env.DB.batch(keys.map((k) => env.DB.prepare("INSERT OR REPLACE INTO bans (key, until, why) VALUES (?, ?, ?)").bind(k, until, why)));
}

async function board(req, env, url) {
  if (!env.DB) return json(req, { error: "게시판 준비 중이에요" }, 503);
  await schema(env);
  const me = await who(req, env);
  const p = url.pathname;
  const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};
  const canSee = (b) => BOARDS[b] && (BOARDS[b].anon || me.uid);

  if (p === "/board/me") return json(req, { login: !!me.uid, admin: me.admin, banned: me.banned, boards: Object.keys(BOARDS).filter(canSee) });

  if (p === "/board/list") {
    const b = url.searchParams.get("b");
    if (!canSee(b)) return json(req, { error: "login" }, 401);
    const before = Number(url.searchParams.get("before")) || 9e15;
    const cat = url.searchParams.get("cat"), mem = url.searchParams.get("m");
    let q = "SELECT * FROM posts WHERE board = ? AND id < ?", args = [b, before];
    if (!me.admin) q += " AND hidden = 0";
    if (cat) { q += " AND cat = ?"; args.push(cat); }
    if (mem) { q += " AND member = ?"; args.push(mem); }
    const pins = before === 9e15 ? (await env.DB.prepare("SELECT * FROM posts WHERE board = ? AND pinned = 1 AND hidden = 0 ORDER BY id DESC").bind(b).all()).results : [];
    const rows = (await env.DB.prepare(q + " AND pinned = 0 ORDER BY id DESC LIMIT 20").bind(...args).all()).results;
    return json(req, { pins: pins.map(pub), posts: rows.map(pub) });
  }

  if (p === "/board/post" && req.method === "GET") {
    const row = await env.DB.prepare("SELECT * FROM posts WHERE id = ?").bind(Number(url.searchParams.get("id"))).first();
    if (!row || !canSee(row.board) || (row.hidden && !me.admin)) return json(req, { error: "없는 글이에요" }, 404);
    const cs = (await env.DB.prepare("SELECT * FROM comments WHERE post = ? ORDER BY id").bind(row.id).all()).results;
    const mine = (x) => !!(me.uid && x.uid === me.uid);
    return json(req, { ...pub(row), body: row.body, mine: mine(row), anonPw: !row.uid,
      comments: cs.filter((c) => !c.hidden || me.admin).map((c) => ({ id: c.id, body: c.body, nick: c.nick, login: !!c.uid, at: c.at, hidden: !!c.hidden, mine: mine(c), anonPw: !c.uid })) });
  }

  if (p === "/board/img") {
    const row = await env.DB.prepare("SELECT p.board, p.hidden, i.type, i.data FROM images i JOIN posts p ON p.id = i.post WHERE i.post = ?").bind(Number(url.searchParams.get("id"))).first();
    if (!row || !canSee(row.board) || row.hidden) return new Response("not found", { status: 404, headers: cors(req) });
    return new Response(new Uint8Array(row.data), { headers: { "Content-Type": row.type, "Cache-Control": "private, max-age=86400", ...cors(req) } });
  }

  if (req.method !== "POST") return json(req, { error: "not found" }, 404);
  if (me.banned) return json(req, { error: `신고가 많아 ${new Date(me.banned + 9 * 36e5).toISOString().slice(0, 10)}까지 글을 쓸 수 없어요` }, 403);

  // 하루 글·댓글 수 제한 (같은 IP·기기·계정 기준)
  const day = Date.now() - 864e5;
  const limitOk = async () => {
    const n = await env.DB.prepare("SELECT (SELECT COUNT(*) FROM posts WHERE at > ? AND (dev = ? OR uid = ?)) + (SELECT COUNT(*) FROM comments WHERE at > ? AND (dev = ? OR uid = ?)) AS n")
      .bind(day, me.dev, me.uid || "-", day, me.dev, me.uid || "-").first("n");
    return n < (me.uid ? LIMIT.user : LIMIT.anon) * 2 || me.admin;
  };
  const checkText = (t) => {
    if (PRIVATE.test(t)) return "전화번호·계좌·메신저 아이디 같은 개인정보는 쓸 수 없어요";
    if (!me.uid && LINK.test(t)) return "링크는 구글 로그인 후 넣을 수 있어요";
    return "";
  };

  // 익명은 사람 확인(Turnstile) 통과해야 글·댓글·신고 가능
  if (!me.uid && ["/board/write", "/board/comment", "/board/report"].includes(p) && env.TURNSTILE_SECRET) {
    const fd = new FormData();
    fd.append("secret", env.TURNSTILE_SECRET);
    fd.append("response", String(body.ts || ""));
    const v = await (await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: fd })).json().catch(() => ({}));
    if (!v.success) return json(req, { error: "사람 확인을 다시 해 주세요" }, 400);
  }

  if (p === "/board/write") {
    const b = body.board;
    if (!BOARDS[b]) return json(req, { error: "게시판을 골라 주세요" }, 400);
    if (!BOARDS[b].anon && !me.uid) return json(req, { error: "login" }, 401);
    const cat = BOARDS[b].cats.includes(body.cat) ? body.cat : BOARDS[b].cats[0];
    const title = clean(body.title, 80), text = clean(body.body, 3000), nick = clean(body.nick, 16) || "익명";
    if (!title || !text) return json(req, { error: "제목과 내용을 써 주세요" }, 400);
    const bad = checkText(title + "\n" + text);
    if (bad) return json(req, { error: bad }, 400);
    if (!me.uid && String(body.pw || "").length < 4) return json(req, { error: "비밀번호를 4자 이상 써 주세요" }, 400);
    if (!(await limitOk())) return json(req, { error: "오늘은 더 쓸 수 없어요 (하루 제한)" }, 429);
    let img = null;
    if (body.image && me.uid) {
      const m = String(body.image).match(/^data:(image\/(jpeg|png|webp));base64,(.+)$/);
      if (!m) return json(req, { error: "사진 형식을 확인해 주세요" }, 400);
      img = { type: m[1], data: Uint8Array.from(atob(m[3]), (c) => c.charCodeAt(0)) };
      if (img.data.length > 700000) return json(req, { error: "사진이 너무 커요" }, 400);
    }
    const r = await env.DB.prepare(`INSERT INTO posts (board, cat, member, title, body, nick, pw, uid, ip, dev, img, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(b, cat, clean(body.member, 12), title, text, nick, me.uid ? null : await pwHash(env, body.pw), me.uid, null, me.dev, img ? 1 : 0, Date.now()).run();
    const id = r.meta.last_row_id;
    if (img) await env.DB.prepare("INSERT INTO images (post, type, data) VALUES (?, ?, ?)").bind(id, img.type, img.data).run();
    return json(req, { ok: true, id });
  }

  if (p === "/board/comment") {
    const row = await env.DB.prepare("SELECT * FROM posts WHERE id = ? AND hidden = 0").bind(Number(body.post)).first();
    if (!row || !canSee(row.board)) return json(req, { error: "login" }, 401);
    const text = clean(body.body, 1000), nick = clean(body.nick, 16) || "익명";
    if (!text) return json(req, { error: "내용을 써 주세요" }, 400);
    const bad = checkText(text);
    if (bad) return json(req, { error: bad }, 400);
    if (!me.uid && String(body.pw || "").length < 4) return json(req, { error: "비밀번호를 4자 이상 써 주세요" }, 400);
    if (!(await limitOk())) return json(req, { error: "오늘은 더 쓸 수 없어요 (하루 제한)" }, 429);
    await env.DB.batch([
      env.DB.prepare("INSERT INTO comments (post, body, nick, pw, uid, ip, dev, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        .bind(row.id, text, nick, me.uid ? null : await pwHash(env, body.pw), me.uid, null, me.dev, Date.now()),
      env.DB.prepare("UPDATE posts SET comments = comments + 1 WHERE id = ?").bind(row.id),
    ]);
    return json(req, { ok: true });
  }

  if (p === "/board/edit") {
    const row = await env.DB.prepare("SELECT * FROM posts WHERE id = ?").bind(Number(body.id)).first();
    if (!row || !(me.admin || (me.uid && row.uid === me.uid))) return json(req, { error: "수정은 구글 로그인한 글쓴이만 할 수 있어요" }, 403);
    const title = clean(body.title, 80), text = clean(body.body, 3000);
    const bad = checkText(title + "\n" + text);
    if (!title || !text || bad) return json(req, { error: bad || "제목과 내용을 써 주세요" }, 400);
    await env.DB.prepare("UPDATE posts SET title = ?, body = ?, edited = ? WHERE id = ?").bind(title, text, Date.now(), row.id).run();
    return json(req, { ok: true });
  }

  if (p === "/board/delete") {
    const isC = !!body.comment, table = isC ? "comments" : "posts";
    const row = await env.DB.prepare(`SELECT * FROM ${table} WHERE id = ?`).bind(Number(isC ? body.comment : body.id)).first();
    if (!row) return json(req, { error: "없는 글이에요" }, 404);
    const ok = me.admin || (me.uid && row.uid === me.uid) || (!row.uid && row.pw && row.pw === (await pwHash(env, String(body.pw || ""))));
    if (!ok) return json(req, { error: "비밀번호가 달라요" }, 403);
    if (isC) await env.DB.batch([env.DB.prepare("DELETE FROM comments WHERE id = ?").bind(row.id), env.DB.prepare("UPDATE posts SET comments = comments - 1 WHERE id = ?").bind(row.post)]);
    else await env.DB.batch([env.DB.prepare("DELETE FROM posts WHERE id = ?").bind(row.id), env.DB.prepare("DELETE FROM comments WHERE post = ?").bind(row.id), env.DB.prepare("DELETE FROM images WHERE post = ?").bind(row.id)]);
    return json(req, { ok: true });
  }

  if (p === "/board/report") {
    const isC = !!body.comment, kind = isC ? "c" : "p", table = isC ? "comments" : "posts";
    const id = Number(isC ? body.comment : body.id);
    const row = await env.DB.prepare(`SELECT * FROM ${table} WHERE id = ?`).bind(id).first();
    if (!row) return json(req, { error: "없는 글이에요" }, 404);
    const reporter = me.uid ? `u:${me.uid}` : `d:${me.dev}`;  // 같은 사람(계정·기기) 신고는 한 번만
    if ([row.uid && `u:${row.uid}`, `d:${row.dev}`].includes(reporter)) return json(req, { error: "내 글은 신고할 수 없어요" }, 400);
    const r = await env.DB.prepare("INSERT OR IGNORE INTO reports (kind, target, who, at) VALUES (?, ?, ?, ?)").bind(kind, id, reporter, Date.now()).run();
    if (!r.meta.changes) return json(req, { ok: true, already: true });
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM reports WHERE kind = ? AND target = ?").bind(kind, id).first("n");
    await env.DB.prepare(`UPDATE ${table} SET reports = ? ${n >= 3 ? ", hidden = 1" : ""} WHERE id = ?`).bind(n, id).run();
    if (n >= 3) await banAuthor(env, row, `신고 3회 (${kind}${id})`);
    return json(req, { ok: true, hidden: n >= 3 });
  }

  if (p === "/board/admin") {
    if (!me.admin) return json(req, { error: "forbidden" }, 403);
    const id = Number(body.id), table = body.comment ? "comments" : "posts";
    const row = id ? await env.DB.prepare(`SELECT * FROM ${table} WHERE id = ?`).bind(id).first() : null;
    if (body.action === "pin" || body.action === "unpin") await env.DB.prepare("UPDATE posts SET pinned = ? WHERE id = ?").bind(body.action === "pin" ? 1 : 0, id).run();
    else if (body.action === "hide" || body.action === "show") await env.DB.prepare(`UPDATE ${table} SET hidden = ? WHERE id = ?`).bind(body.action === "hide" ? 1 : 0, id).run();
    else if (body.action === "ban" && row) await banAuthor(env, row, "관리자");
    else if (body.action === "unban" && row) {
      const keys = [row.uid && `u:${row.uid}`, `d:${row.dev}`].filter(Boolean);
      await env.DB.prepare(`DELETE FROM bans WHERE key IN (${keys.map(() => "?").join(",")})`).bind(...keys).run();
    } else return json(req, { error: "unknown action" }, 400);
    return json(req, { ok: true });
  }
  return json(req, { error: "not found" }, 404);
}

// ---------- X(트위터) 자동 글: 수집기가 초안을 만들고, 관리자가 tweet.html에서 확인 후 올림 ----------
// secrets: TWEET_KEY(관리 비밀번호) · X_API_KEY · X_API_SECRET (+ 올릴 계정은 tweet.html의 'X 계정 연결', 또는 X_ACCESS_TOKEN·X_ACCESS_SECRET)
const sameKey = async (a, b) => typeof a === "string" && !!b && a.length === b.length
  && hex(await crypto.subtle.digest("SHA-256", enc.encode(a))) === hex(await crypto.subtle.digest("SHA-256", enc.encode(b)));
const pct = (s) => encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());

// OAuth 1.0a 서명 헤더 (extra: oauth_callback·oauth_verifier 등, 본문이 JSON이면 서명에 안 들어감)
async function oauthHeader(env, method, url, { token = "", tokenSecret = "", extra = {}, body = {} } = {}) {
  const o = { oauth_consumer_key: env.X_API_KEY, oauth_nonce: crypto.randomUUID().replace(/-/g, ""), oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)), oauth_version: "1.0", ...(token ? { oauth_token: token } : {}), ...extra };
  const all = { ...o, ...body };  // 폼 본문 파라미터도 서명에 포함 (헤더엔 안 넣음)
  const params = Object.keys(all).sort().map((k) => `${pct(k)}=${pct(all[k])}`).join("&");
  const base = `${method}&${pct(url)}&${pct(params)}`;
  const key = await crypto.subtle.importKey("raw", enc.encode(`${pct(env.X_API_SECRET)}&${pct(tokenSecret)}`), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  o.oauth_signature = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(base)))));
  return "OAuth " + Object.keys(o).sort().map((k) => `${pct(k)}="${pct(o[k])}"`).join(", ");
}
// 글 올릴 계정: tweet.html에서 'X 계정 연결'로 저장한 계정 → 없으면 Cloudflare 시크릿(X_ACCESS_TOKEN·X_ACCESS_SECRET)
async function xAccount(env) {
  const a = await env.SUBS.get("_twacct", "json");
  if (a && ((a.token && a.secret) || (a.v === 2 && a.refresh))) return a;
  return env.X_ACCESS_TOKEN && env.X_ACCESS_SECRET ? { token: env.X_ACCESS_TOKEN, secret: env.X_ACCESS_SECRET, screen_name: "" } : null;
}

// ---- OAuth 2.0 (PKCE) 연결: OAuth 1.0a 교환이 X 쪽 500으로 막혀서 대신 씀 ----
// 변수 X_CLIENT_ID · 비밀 X_CLIENT_SECRET (X 콘솔 → 앱 → OAuth 2.0 키), 콜백 https://push.a2osoul-tracker.com/tweet/callback2
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const o2Auth = (env) => ({ Authorization: "Basic " + btoa(`${env.X_CLIENT_ID}:${env.X_CLIENT_SECRET || ""}`), "Content-Type": "application/x-www-form-urlencoded" });
async function x2Connect(env, origin) {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  await env.SUBS.put(`_tw2:${state}`, verifier, { expirationTtl: 900 });
  const q = new URLSearchParams({ response_type: "code", client_id: env.X_CLIENT_ID, redirect_uri: `${origin}/tweet/callback2`,
    scope: "tweet.read tweet.write users.read media.write offline.access", state, code_challenge: b64url(await crypto.subtle.digest("SHA-256", enc.encode(verifier))),
    code_challenge_method: "S256" });
  return `https://x.com/i/oauth2/authorize?${q}`;
}
async function x2Save(env, j, screen_name) {
  const acct = { v: 2, access: j.access_token, refresh: j.refresh_token, exp: Date.now() + (Number(j.expires_in) || 7200) * 1000 - 60000, screen_name, at: Date.now() };
  await env.SUBS.put("_twacct", JSON.stringify(acct));
  return acct;
}
async function x2Callback(env, url) {
  const back = (m) => Response.redirect(`https://a2osoul-tracker.com/tweet.html?x=${encodeURIComponent(m)}`, 302);
  if (url.searchParams.get("error")) return back("취소했어요");
  const state = url.searchParams.get("state") || "", code = url.searchParams.get("code") || "";
  const verifier = await env.SUBS.get(`_tw2:${state}`);
  if (!verifier || !code) return back("연결 시간이 지났어요. 다시 눌러 주세요");
  await env.SUBS.delete(`_tw2:${state}`);
  const r = await fetch("https://api.x.com/2/oauth2/token", { method: "POST", headers: o2Auth(env),
    body: new URLSearchParams({ grant_type: "authorization_code", code, redirect_uri: `${url.origin}/tweet/callback2`, code_verifier: verifier, client_id: env.X_CLIENT_ID }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.access_token) return back(`연결 실패 (OAuth2 ${r.status} ${(j.error_description || j.error || "").slice(0, 120)})`);
  let name = "";
  try { name = ((await (await fetch("https://api.x.com/2/users/me", { headers: { Authorization: `Bearer ${j.access_token}` } })).json()).data || {}).username || ""; } catch (_) {}
  await x2Save(env, j, name);
  return back(`@${name} 연결됐어요`);
}
// OAuth2 토큰은 2시간이면 만료 → 올릴 때 새로 받기 (refresh token은 쓸 때마다 바뀌어서 같이 저장)
async function x2Fresh(env, acct) {
  if (acct.exp > Date.now()) return acct;
  const r = await fetch("https://api.x.com/2/oauth2/token", { method: "POST", headers: o2Auth(env),
    body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: acct.refresh, client_id: env.X_CLIENT_ID }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.access_token) throw new Error(`X 로그인이 만료됐어요 — 'X 계정 연결'을 다시 눌러 주세요 (${r.status})`);
  return x2Save(env, j, acct.screen_name);
}

// 사진 올리기 (OAuth 2.0 + media.write 권한) → media id. 실패하면 null (글만 올림)
async function uploadImage(env, acct, imageUrl) {
  try {
    if (acct.v !== 2 || !/^https:\/\/a2osoul-tracker\.com\//.test(imageUrl || "")) return null;
    const img = await fetch(imageUrl);
    if (!img.ok) return null;
    const fd = new FormData();
    fd.append("media", new Blob([await img.arrayBuffer()], { type: img.headers.get("content-type") || "image/jpeg" }), "image.jpg");
    fd.append("media_category", "tweet_image");
    const r = await fetch("https://api.x.com/2/media/upload", { method: "POST", headers: { Authorization: `Bearer ${(await x2Fresh(env, acct)).access}` }, body: fd });
    const j = await r.json().catch(() => ({}));
    return (j.data && (j.data.id || j.data.media_id)) || null;
  } catch (_) { return null; }
}

async function postTweet(env, text, imageUrl) {
  const acct = await xAccount(env);
  if (!acct) throw new Error("연결된 X 계정이 없어요");
  const url = "https://api.x.com/2/tweets";
  const mediaId = imageUrl ? await uploadImage(env, acct, imageUrl) : null;
  const auth = acct.v === 2 ? `Bearer ${(await x2Fresh(env, acct)).access}` : await oauthHeader(env, "POST", url, { token: acct.token, tokenSecret: acct.secret });
  const r = await fetch(url, { method: "POST", headers: { Authorization: auth, "Content-Type": "application/json" },
    body: JSON.stringify(mediaId ? { text, media: { media_ids: [String(mediaId)] } } : { text }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j.detail || j.title || JSON.stringify(j)).slice(0, 200) || String(r.status));
  return j.data && j.data.id;
}

// 리트윗: 매체 글 초안은 새 글 대신 원문을 그대로 리트윗 (트래커 계정 = 연결된 계정)
async function xAuth(env, acct, method, url) {
  return acct.v === 2 ? `Bearer ${(await x2Fresh(env, acct)).access}` : await oauthHeader(env, method, url, { token: acct.token, tokenSecret: acct.secret });
}
async function retweet(env, tweetId) {
  const acct = await xAccount(env);
  if (!acct) throw new Error("연결된 X 계정이 없어요");
  const meUrl = "https://api.x.com/2/users/me";
  const me = await (await fetch(meUrl, { headers: { Authorization: await xAuth(env, acct, "GET", meUrl) } })).json().catch(() => ({}));
  if (!me.data || !me.data.id) throw new Error("내 계정 정보를 못 읽었어요");
  const url = `https://api.x.com/2/users/${me.data.id}/retweets`;
  const r = await fetch(url, { method: "POST", headers: { Authorization: await xAuth(env, acct, "POST", url), "Content-Type": "application/json" },
    body: JSON.stringify({ tweet_id: tweetId }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j.detail || j.title || JSON.stringify(j)).slice(0, 200) || String(r.status));
  return tweetId;
}

// X 계정 연결 (OAuth 1.0a 3-legged): /tweet/connect → X 로그인·허용 → /tweet/callback → 토큰을 KV에 저장
async function xConnect(env, origin) {
  const url = "https://api.x.com/oauth/request_token";
  const auth = await oauthHeader(env, "POST", url, { extra: { oauth_callback: `${origin}/tweet/callback` } });
  const r = await fetch(url, { method: "POST", headers: { Authorization: auth } });
  const q = new URLSearchParams(await r.text());
  if (!r.ok || !q.get("oauth_token")) throw new Error(`X 연결 시작 실패 (${r.status}) — 콜백 URI 등록을 확인해 주세요`);
  await env.SUBS.put(`_twreq:${q.get("oauth_token")}`, q.get("oauth_token_secret") || "", { expirationTtl: 900 });
  return `https://api.x.com/oauth/authorize?oauth_token=${encodeURIComponent(q.get("oauth_token"))}&force_login=true`;
}
async function xCallback(env, url) {
  const back = (m) => Response.redirect(`https://a2osoul-tracker.com/tweet.html?x=${encodeURIComponent(m)}`, 302);
  const tok = url.searchParams.get("oauth_token") || "", ver = url.searchParams.get("oauth_verifier") || "";
  if (url.searchParams.get("denied")) return back("취소했어요");
  const sec = await env.SUBS.get(`_twreq:${tok}`);
  if (sec === null || !ver) return back("연결 시간이 지났어요. 다시 눌러 주세요");
  await env.SUBS.delete(`_twreq:${tok}`);
  // access_token 교환: X 문서 방식(쿼리에 oauth_token·oauth_verifier) → 안 되면 서명 헤더 방식, api.x.com → api.twitter.com 순서로 시도
  let q = null, last = "";
  for (const host of ["https://api.x.com", "https://api.twitter.com"]) {
    const au = `${host}/oauth/access_token`;
    const form = { "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "a2osoul-tracker/1.0" };
    const tries = [
      // ① 서명 헤더 + 본문에 oauth_verifier (가장 흔한 라이브러리 방식)
      ["form", async () => fetch(au, { method: "POST", body: `oauth_verifier=${pct(ver)}`,
        headers: { ...form, Authorization: await oauthHeader(env, "POST", au, { token: tok, tokenSecret: sec, body: { oauth_verifier: ver } }) } })],
      // ② X 문서 예시 (쿼리)
      ["query", () => fetch(`${au}?oauth_token=${encodeURIComponent(tok)}&oauth_verifier=${encodeURIComponent(ver)}`, { method: "POST", headers: form })],
      // ③ 서명 헤더만
      ["header", async () => fetch(au, { method: "POST", headers: { ...form, Authorization: await oauthHeader(env, "POST", au, { token: tok, tokenSecret: sec, extra: { oauth_verifier: ver } }) } })],
    ];
    for (const [name, go] of tries) {
      const r = await go();
      const txt = await r.text();
      const p = new URLSearchParams(txt);
      if (r.ok && p.get("oauth_token") && p.get("oauth_token_secret")) { q = p; break; }
      const why = /<html/i.test(txt) ? "X 오류 페이지" : txt.replace(/\s+/g, " ").slice(0, 80);
      last += `${last ? " / " : ""}${host.replace("https://", "")} ${name} ${r.status} ${why}`;
      console.log(`access_token 실패 ${host} ${name}: ${r.status} ${txt.slice(0, 300)}`);
    }
    if (q) break;
  }
  if (!q) return back(`연결 실패 — ${last.slice(0, 400)}`);
  await env.SUBS.put("_twacct", JSON.stringify({ token: q.get("oauth_token"), secret: q.get("oauth_token_secret"), screen_name: q.get("screen_name") || "", at: Date.now() }));
  return back(`@${q.get("screen_name") || ""} 연결됐어요`);
}

async function tweets(req, env, url) {
  const p = url.pathname;
  if (req.method === "POST" && p === "/tweet/drafts") { // 수집기(GitHub Actions)만
    if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
    const b = await req.json().catch(() => ({}));
    let added = 0, posted = 0;
    const acct = await xAccount(env);
    const canPost = !!(acct && (acct.v === 2 || (env.X_API_KEY && env.X_API_SECRET)));
    for (const d of (b.drafts || []).slice(0, 20)) {
      if (!d || typeof d.text !== "string" || !d.key) continue;
      const id = (await sha("tw:" + d.key)).slice(0, 16);
      if (await env.SUBS.get(`_tw:${id}`)) continue;
      const rec = { id, key: String(d.key).slice(0, 120), kind: String(d.kind || ""), text: d.text.slice(0, 1000), status: "pending", at: Date.now(),
        ...(typeof d.image === "string" && /^https:\/\/a2osoul-tracker\.com\//.test(d.image) ? { image: d.image } : {}) };
      if (d.auto && canPost) {  // 확실한 정보(일정·생일·조회수)는 확인 없이 바로 올림 — 실패하면 초안으로 남김
        try { rec.tweet = await postTweet(env, rec.text, rec.image); rec.status = "posted"; rec.auto = true; rec.posted = Date.now(); posted++; }
        catch (e) { rec.error = String(e.message || e).slice(0, 200); }
      }
      await env.SUBS.put(`_tw:${id}`, JSON.stringify(rec), { expirationTtl: 3 * 86400 });
      if (rec.status === "pending") added++;
    }
    return json(req, { ok: true, added, posted });
  }
  if (req.method === "POST" && p === "/tweet/xstat") { // 수집기(GitHub Actions)만 — X 사용량 하루치 합산
    if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
    const b = await req.json().catch(() => ({}));
    const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
    const x = (await env.SUBS.get("_xstat", "json")) || { days: {} };
    const t = x.days[day] || { reads: 0, users: 0 };
    t.reads += Math.max(0, Number(b.reads) || 0); t.users += Math.max(0, Number(b.users) || 0);
    x.days[day] = t;
    for (const k of Object.keys(x.days).sort().slice(0, -14)) delete x.days[k];
    let alert = false;
    if (Number(b.err402) > 0) { alert = x.err_day !== day; if (!x.err_at) x.err_at = Date.now(); x.err_day = day; }
    else if ((Number(b.reads) || 0) + (Number(b.users) || 0) > 0) { x.err_at = 0; }  // 다시 읽히면 회복
    x.at = Date.now();
    await env.SUBS.put("_xstat", JSON.stringify(x));
    return json(req, { ok: true, alert });
  }
  if (req.method === "GET" && p === "/tweet/callback") return xCallback(env, url);
  if (req.method === "GET" && p === "/tweet/callback2") return x2Callback(env, url);
  const b = req.method === "POST" ? await req.json().catch(() => ({})) : {};
  if (!(await sameKey(b.key, env.TWEET_KEY))) return json(req, { error: "비밀번호가 달라요" }, 403);
  const appOk = !!(env.X_API_KEY && env.X_API_SECRET);
  if (p === "/tweet/connect") {
    if (!appOk && !env.X_CLIENT_ID) return json(req, { error: "X_API_KEY·X_API_SECRET이 아직 없어요" }, 503);
    if (env.X_CLIENT_ID) return json(req, { url: await x2Connect(env, url.origin) });  // OAuth 2.0 우선
    try { return json(req, { url: await xConnect(env, url.origin) }); } catch (e) { return json(req, { error: e.message }, 502); }
  }
  if (p === "/tweet/disconnect") { await env.SUBS.delete("_twacct"); return json(req, { ok: true }); }
  if (p === "/tweet/stats") {  // 알림 구독자 수 (관리 비밀번호로만) — 사람 정보 없이 숫자만
    const topics = {}, langs = {};
    let total = 0, cursor;
    do {
      const page = await env.SUBS.list({ cursor });
      const keys = page.keys.filter((k) => !k.name.startsWith("_"));
      // 메타데이터 없는 옛 구독만 한꺼번에 읽기 (하나씩 읽으면 느림)
      const old = await Promise.all(keys.map((k) => (k.metadata && k.metadata.e) ? null : env.SUBS.get(k.name, "json")));
      for (let i = 0; i < keys.length; i++) {
        let m = keys[i].metadata;
        if (!(m && m.e)) { const v = old[i]; if (!v) continue; m = { t: v.topics, l: v.lang }; }
        total++;
        for (const t of m.t || []) topics[t] = (topics[t] || 0) + 1;
        langs[m.l || "?"] = (langs[m.l || "?"] || 0) + 1;
      }
      cursor = page.list_complete ? null : page.cursor;
    } while (cursor);
    // 날짜별 기록: 하루 한 번만 씀 (KST)
    const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
    const hist = (await env.SUBS.get("_substats", "json")) || [];
    if (!hist.length || hist[hist.length - 1].d !== day) { hist.push({ d: day, n: total }); await env.SUBS.put("_substats", JSON.stringify(hist.slice(-120))); }
    else if (hist[hist.length - 1].n !== total) { hist[hist.length - 1].n = total; await env.SUBS.put("_substats", JSON.stringify(hist.slice(-120))); }
    return json(req, { total, topics, langs, history: hist.slice(-30), x: (await env.SUBS.get("_xstat", "json")) || null });
  }
  if (p === "/tweet/list") {
    const out = [];
    let cursor;
    do {
      const page = await env.SUBS.list({ prefix: "_tw:", cursor });
      const vals = await Promise.all(page.keys.map((k) => env.SUBS.get(k.name, "json")));  // 한꺼번에 (하나씩 읽으면 느림)
      for (const v of vals) if (v) out.push(v);
      cursor = page.list_complete ? null : page.cursor;
    } while (cursor);
    const acct = await xAccount(env);
    return json(req, { ready: !!(acct && (acct.v === 2 || appOk)), account: acct ? (acct.screen_name || "(시크릿에 넣은 계정)") : "", connected: !!(await env.SUBS.get("_twacct")),
      drafts: out.sort((a, c) => c.at - a.at) });
  }
  const k = `_tw:${String(b.id || "").replace(/[^0-9a-f]/g, "")}`;
  const d = await env.SUBS.get(k, "json");
  if (!d) return json(req, { error: "이미 지났거나 없는 초안이에요" }, 404);
  if (p === "/tweet/skip") {
    await env.SUBS.put(k, JSON.stringify({ ...d, status: "skipped" }), { expirationTtl: 86400 });
    return json(req, { ok: true });
  }
  if (p === "/tweet/retweet") {
    const ref = (String(d.key).match(/status\/(\d+)/) || [])[1];
    if (!ref) return json(req, { error: "리트윗할 원문을 못 찾았어요" }, 400);
    if (d.status === "posted") return json(req, { error: "이미 처리한 초안이에요" }, 409);
    try {
      await retweet(env, ref);
      await env.SUBS.put(k, JSON.stringify({ ...d, status: "posted", tweet: ref, retweet: true, posted: Date.now() }), { expirationTtl: 3 * 86400 });
      return json(req, { ok: true, tweet: ref });
    } catch (e) {
      return json(req, { error: `리트윗 실패: ${e.message}` }, 502);
    }
  }
  if (p === "/tweet/post") {
    if (d.status === "posted") return json(req, { error: "이미 올린 글이에요" }, 409);
    const ac = await xAccount(env);
    if (!ac || (ac.v !== 2 && !appOk)) return json(req, { error: "X 계정이 아직 연결되지 않았어요" }, 503);
    const text = typeof b.text === "string" && b.text.trim() ? b.text.trim().slice(0, 1000) : d.text;
    try {
      const tid = await postTweet(env, text, b.noImage ? null : d.image);
      await env.SUBS.put(k, JSON.stringify({ ...d, text, status: "posted", tweet: tid, posted: Date.now() }), { expirationTtl: 3 * 86400 });
      return json(req, { ok: true, tweet: tid });
    } catch (e) {
      return json(req, { error: `X 올리기 실패: ${e.message}` }, 502);
    }
  }
  return json(req, { error: "not found" }, 404);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });

    if (url.pathname === "/yt-hook") return youtubeHook(req, env);
    if (url.pathname.startsWith("/board/")) return board(req, env, url);
    if (url.pathname.startsWith("/tweet/")) return tweets(req, env, url);
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
      let topics = (Array.isArray(body.topics) ? body.topics : TOPICS).filter((t) => TOPICS.includes(t));
      let lang = LANGS.includes(body.lang) ? body.lang : "en";
      const id = await idOf(sub.endpoint);
      // 트윗 초안 알림(tweet): tweet.html에서 관리 비밀번호가 맞을 때만 켜짐. 기존 알림 주제는 그대로 두고 더하기만,
      // 사이트에서 알림 주제를 바꿀 때도 유지 (tweetOff로만 끔)
      const prev = await env.SUBS.get(id, "json");
      if (Array.isArray(body.topics) && body.topics.includes("tweet")) {
        if (!(await sameKey(body.key, env.TWEET_KEY))) return json(req, { error: "비밀번호가 달라요" }, 403);
        topics = [...new Set([...((prev && prev.topics) || []), "tweet"])];
        lang = (prev && prev.lang) || lang;
      } else if (body.tweetOff) {
        if (!(await sameKey(body.key, env.TWEET_KEY))) return json(req, { error: "비밀번호가 달라요" }, 403);
        topics = ((prev && prev.topics) || []).filter((t) => t !== "tweet");
        lang = (prev && prev.lang) || lang;
      } else if (prev && (prev.topics || []).includes("tweet")) topics.push("tweet");
      const val = { sub: { endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth } }, topics, lang, at: Date.now() };
      await env.SUBS.put(id, JSON.stringify(val), { metadata: subMeta(val) });
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
      // 순위 또는 스트리밍 수(Spotify 일간 등) — 스트리밍 수면 streams만
      const streams = b.streams == null ? null : Number(b.streams);
      const rank = streams != null ? null : b.rank === null ? null : Number(b.rank);
      const okStreams = streams != null && Number.isInteger(streams) && streams >= 0 && streams <= 1e9;
      if (!song || !service || !(okStreams || rank === null || (Number.isInteger(rank) && rank >= 1 && rank <= 300))) return json(req, { error: "곡·차트·순위(또는 스트리밍 수)를 확인해 주세요" }, 400);
      const at = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16).replace("T", " "); // KST
      const list = (await env.SUBS.get("_charts", "json")) || [];
      list.push(okStreams ? { song, service, streams, at, ...(b.date && /^\d{4}-\d{2}-\d{2}$/.test(b.date) ? { date: b.date } : {}) } : { song, service, rank, at });
      await env.SUBS.put("_charts", JSON.stringify(list.slice(-2000)));
      await caches.default.delete(CHART_CACHE);
      // 바로 수집 실행 → 알림 (2분에 한 번만)
      if (Date.now() - (Number(await env.SUBS.get("_chart_dispatch")) || 0) > 120000) {
        await env.SUBS.put("_chart_dispatch", String(Date.now()), { expirationTtl: 3600 });
        await dispatch(env, "차트 입력");
      }
      return json(req, { ok: true, at });
    }
    if (req.method === "GET" && url.pathname === "/charts") {
      return new Response(await chartsBody(env), { headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=60", ...cors(req) } });
    }

    // 한눈에 화면 스타일(A·B·C) 고른 횟수 — 누가 골랐는지는 저장 안 함
    if (url.pathname === "/style") {
      const ST = ["a", "b", "c"];
      if (req.method === "POST") {
        const { s } = await req.json().catch(() => ({}));
        if (!ST.includes(s)) return json(req, { error: "bad style" }, 400);
        const k = `_style:${s}`;
        await env.SUBS.put(k, String((Number(await env.SUBS.get(k)) || 0) + 1));
        return json(req, { ok: true });
      }
      const out = {};
      for (const s of ST) out[s] = Number(await env.SUBS.get(`_style:${s}`)) || 0;
      return json(req, out);
    }
    if (req.method === "GET" && url.pathname === "/subs") {
      if (!(await isAdmin(req, env))) return json(req, { error: "forbidden" }, 403);
      const out = [];
      let cursor, moved = 0;
      do {
        const page = await env.SUBS.list({ cursor });
        for (const k of page.keys) {
          if (k.name.startsWith("_")) continue; // 내부용 키
          const m = k.metadata;
          if (m && m.e) { out.push({ id: k.name, sub: { endpoint: m.e, keys: { p256dh: m.p, auth: m.a } }, topics: m.t, lang: m.l, at: m.at }); continue; }
          const v = await env.SUBS.get(k.name, "json");  // 예전 구독 — 한 번에 100개까지 메타데이터로 옮김
          if (!v) continue;
          out.push({ id: k.name, ...v });
          if (moved < 100 && subMeta(v)) { await env.SUBS.put(k.name, JSON.stringify(v), { metadata: subMeta(v) }); moved++; }
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

  // Cron Trigger (*/10 * * * *): 10분마다 수집 실행, 3시간마다 포카 확인, 하루 한 번(KST 12시대) YouTube 알림 구독 갱신
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, "10분 정기"));
    const t = new Date(event.scheduledTime);
    if (t.getUTCHours() === 3 && t.getUTCMinutes() < 10) ctx.waitUntil(renewYoutube(env));
    // 포카 템플릿 확인: 3시간마다 (GitHub 자체 예약 실행은 자주 밀리거나 건너뛰어서 여기서 깨움)
    if (t.getUTCHours() % 3 === 0 && t.getUTCMinutes() >= 40 && t.getUTCMinutes() < 50) ctx.waitUntil(dispatch(env, "3시간 정기", "photocards.yml"));
  },
};
