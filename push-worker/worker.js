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
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Device",
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

// ---------- 커뮤니티 게시판 (D1 바인딩 DB) ----------
// 게시판: qna(질문·정보, 익명 가능) / trade(포카 교환, 구글 로그인만 — 익명은 목록도 안 보임)
// 익명은 닉네임+비밀번호. 신원: 구글 sub 해시 / IP 해시 / 기기 ID (화면엔 안 보임, 차단용)
// 신고: 서로 다른 사람 3명 → 글 숨김 + 쓴 사람 30일 차단 (관리자가 풀 수 있음)
// 설정: D1 바인딩 DB / 변수 GOOGLE_CLIENT_ID / 비밀 ADMIN_EMAILS(쉼표로) / 비밀 BOARD_SALT(아무 긴 문자열)
const BOARDS = { qna: { cats: ["질문", "정보", "후기"], anon: true }, trade: { cats: ["구해요", "드려요", "교환해요"], anon: false } };
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
  const ip = await sha(salt + "ip:" + (req.headers.get("CF-Connecting-IP") || ""));
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
  const keys = [uid && `u:${uid}`, `i:${ip}`, `d:${dev}`].filter(Boolean);
  const ban = await env.DB.prepare(`SELECT until FROM bans WHERE key IN (${keys.map(() => "?").join(",")}) AND until > ? ORDER BY until DESC LIMIT 1`)
    .bind(...keys, Date.now()).first();
  return { uid, ip, dev, admin, banned: ban ? ban.until : 0, keys };
}
const pwHash = (env, pw) => sha((env.BOARD_SALT || "a2o") + "pw:" + pw);
const clean = (s, n) => String(s || "").replace(/[\u0000-\u0008\u000b-\u001f]/g, "").trim().slice(0, n);
const pub = (p) => ({ id: p.id, board: p.board, cat: p.cat, member: p.member, title: p.title, nick: p.nick, login: !!p.uid,
  img: !!p.img, pinned: !!p.pinned, hidden: !!p.hidden, comments: p.comments, at: p.at, edited: p.edited });

async function banAuthor(env, row, why) {
  const until = Date.now() + BAN_DAYS * 864e5;
  const keys = [row.uid && `u:${row.uid}`, row.ip && `i:${row.ip}`, row.dev && `d:${row.dev}`].filter(Boolean);
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
    const n = await env.DB.prepare("SELECT (SELECT COUNT(*) FROM posts WHERE at > ? AND (ip = ? OR dev = ? OR uid = ?)) + (SELECT COUNT(*) FROM comments WHERE at > ? AND (ip = ? OR dev = ? OR uid = ?)) AS n")
      .bind(day, me.ip, me.dev, me.uid || "-", day, me.ip, me.dev, me.uid || "-").first("n");
    return n < (me.uid ? LIMIT.user : LIMIT.anon) * 2 || me.admin;
  };
  const checkText = (t) => {
    if (PRIVATE.test(t)) return "전화번호·계좌·메신저 아이디 같은 개인정보는 쓸 수 없어요";
    if (!me.uid && LINK.test(t)) return "링크는 구글 로그인 후 넣을 수 있어요";
    return "";
  };

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
      .bind(b, cat, clean(body.member, 12), title, text, nick, me.uid ? null : await pwHash(env, body.pw), me.uid, me.ip, me.dev, img ? 1 : 0, Date.now()).run();
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
        .bind(row.id, text, nick, me.uid ? null : await pwHash(env, body.pw), me.uid, me.ip, me.dev, Date.now()),
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
    const reporter = me.uid ? `u:${me.uid}` : `i:${me.ip}`;  // 같은 사람(계정·IP) 신고는 한 번만
    if ([row.uid && `u:${row.uid}`, `i:${row.ip}`].includes(reporter)) return json(req, { error: "내 글은 신고할 수 없어요" }, 400);
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
      const keys = [row.uid && `u:${row.uid}`, `i:${row.ip}`, `d:${row.dev}`].filter(Boolean);
      await env.DB.prepare(`DELETE FROM bans WHERE key IN (${keys.map(() => "?").join(",")})`).bind(...keys).run();
    } else return json(req, { error: "unknown action" }, 400);
    return json(req, { ok: true });
  }
  return json(req, { error: "not found" }, 404);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });

    if (url.pathname === "/yt-hook") return youtubeHook(req, env);
    if (url.pathname.startsWith("/board/")) return board(req, env, url);
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
