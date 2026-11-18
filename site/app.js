// ---------- 언어 ----------
const LANGS = ["ko", "en", "ja", "zh", "es", "id", "th", "pt"];
const LOCALES = { ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN", es: "es-ES", id: "id-ID", th: "th-TH", pt: "pt-BR" };
// 기기별 설정(최애·본 영상) — 막혀 있어도 사이트는 그대로 동작
const pref = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* 무시 */ } },
};
const LANG = (() => {
  try {
    const saved = localStorage.getItem("lang");
    if (LANGS.includes(saved)) return saved;
  } catch (_) { /* 저장소 막힘 */ }
  const nav = (navigator.language || "ko").slice(0, 2);
  return LANGS.includes(nav) ? nav : "en";
})();
function t(key, vars = {}) {
  const dict = window.I18N[LANG] || window.I18N.ko;
  let s = dict[key] ?? window.I18N.ko[key] ?? key;
  if (typeof s !== "string") return s;
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}
document.documentElement.lang = LANG === "pt" ? "pt-BR" : LANG;
document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
(function langSelect() {
  const sel = document.getElementById("lang");
  for (const l of LANGS) {
    const o = document.createElement("option");
    o.value = l; o.textContent = window.I18N[l].lang; o.selected = l === LANG;
    sel.append(o);
  }
  sel.addEventListener("change", () => {
    try { localStorage.setItem("lang", sel.value); } catch (_) { /* 무시 */ }
    location.reload();
  });
})();

// ---------- 앱 설치(PWA) ----------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
(function installUI() {
  const btn = document.getElementById("installBtn");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (standalone || !btn) return;
  let deferred = null;
  // 안드로이드·크롬: 설치 프롬프트
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; btn.hidden = false; });
  window.addEventListener("appinstalled", () => { btn.hidden = true; });
  // iOS Safari: 설치 프롬프트가 없어서 안내 팝업
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !/crios|fxios/i.test(navigator.userAgent);
  if (ios) btn.hidden = false;
  btn.addEventListener("click", async () => {
    if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; btn.hidden = true; return; }
    const help = document.getElementById("installHelp");
    help.showModal();
    document.getElementById("installHelpClose").onclick = () => help.close();
  });
})();

(async function () {
  const locale = LOCALES[LANG];
  const fmt = (v) => (v == null ? "–" : Number(v).toLocaleString(locale));
  const compact = new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 });
  const kr = (n) => (LANG === "ko"
    ? (n >= 1e8 ? `${+(n / 1e8).toFixed(2)}억` : n >= 1e4 ? `${+(n / 1e4).toFixed(1)}만` : fmt(n))
    : compact.format(n));
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else n.setAttribute(k, v);
    }
    for (const c of children) if (c != null && c !== false) n.append(c);
    return n;
  };
  const deltaSpan = (d) => (d ? el("span", { class: "delta" }, `+${fmt(d)}`) : null);
  const ytUrl = (id) => `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
  const thumbUrl = (id) => `https://i.ytimg.com/vi/${encodeURIComponent(id)}/mqdefault.jpg`;
  // 외부 링크는 http(s)만 (yml에 잘못된 주소가 들어가도 javascript: 등은 막기)
  const ext = (href, ...children) => el("a", { href: /^https?:\/\//i.test(href || "") ? href : "#", target: "_blank", rel: "noopener" }, ...children);
  const empty = (msg) => el("div", { class: "empty" }, msg);
  // 긴 목록 접기: 앞의 n개만 보이고 '더 보기 (+k)' — 폰에서 세로로 너무 길어지지 않게
  const MOBILE = window.matchMedia("(max-width: 720px)").matches;
  // 음방 생방송 보는 곳 (info.yml show_live) — 제목에 방송 이름이 들어 있으면
  const liveFor = (text) => (data.info?.show_live || []).find((x) => String(text || "").includes(x.show));
  const liveLink = (text, cls = "live-link") => {
    const x = liveFor(text);
    return x ? el("a", { class: cls, href: x.url, target: "_blank", rel: "noopener", title: t("live_note") }, `${t("live_watch")} · ${x.label}`) : null;
  };
  const fold = (box, n) => {
    if (!box) return;
    box.parentElement?.querySelector(`:scope > .fold-more[data-for="${box.id}"]`)?.remove();
    const kids = [...box.children];
    if (kids.length <= n + 1) return;
    kids.slice(n).forEach((k) => k.classList.add("fold-x"));
    const b = el("button", { type: "button", class: "more fold-more", "data-for": box.id }, t("more_n", { n: kids.length - n }));
    b.addEventListener("click", () => { kids.forEach((k) => k.classList.remove("fold-x")); b.remove(); });
    box.after(b);
  };
  const kstFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" });
  const todayKst = kstFmt.format(new Date()); // YYYY-MM-DD
  const nat = (s) => (s || "").split("·").map((x) => (t("nat")[x] || x)).join("·");
  // 내용 번역 (translations.yml): 한국어 원문 그대로 키, 없으면 원문
  let TR = {};
  const tc = (s) => (LANG === "ko" || !s ? s : TR[s]?.[LANG] || TR[s]?.en || s);
  // 자동으로 만든 문구(기록·기념일)는 언어별 틀로
  const tx = (x) => {
    if (x.key) return t(x.key, { n: x.key.startsWith("anniv") ? x.n : fmt(x.n), show: tc(x.show), type: tc(x.type), name: x.name });
    const m = /^(.+) 출연$/.exec(x.title || ""); // 공지에서 뽑은 '뮤직뱅크 출연'
    return m ? t("ev_show", { show: tc(m[1]) }) : tc(x.title);
  };
  // 한국 밖에서 보면 KST 옆에 내 시간도
  const awayFromKst = new Date().getTimezoneOffset() !== -540;
  const localOf = (date, time) => {
    if (!awayFromKst || !date || !time) return "";
    const d = new Date(`${date}T${time}:00+09:00`);
    if (Number.isNaN(d.getTime())) return "";
    return t("local_time", { t: d.toLocaleString(LOCALES[LANG], { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) });
  };
  const kstDate = (s) => new Date(`${s.replace(" ", "T")}${s.length > 10 ? ":00" : "T00:00:00"}+09:00`); // "YYYY-MM-DD[ HH:MM]" KST

  // ---------- 탭 ----------
  const tabs = ["overview", "notice", "cheer", "mv", "members", "fancams", "videos", "guide"];
  const drawn = new Set();
  const drawers = {};
  // 공유 링크: #member/MOON → 멤버 탭, #ep/날짜/방송 → 영상 탭, #cmp/날짜/방송/A/B → 직캠 탭
  const ROUTE_TAB = { member: "members", ep: "videos", cmp: "fancams" };
  const route = () => decodeURIComponent(location.hash.slice(1)).split("/");
  function showTab() {
    const [head] = route();
    const cur = tabs.includes(head) ? head : ROUTE_TAB[head] || "overview";
    document.querySelectorAll("[data-tab]").forEach((s) => (s.hidden = s.dataset.tab !== cur));
    document.querySelectorAll("#tabs a").forEach((a) => {
      const on = a.getAttribute("href") === `#${cur}`;
      a.classList.toggle("on", on);
      if (on) a.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    if (!drawn.has(cur) && drawers[cur] && window.Chart) { drawn.add(cur); drawers[cur](); }
  }
  window.addEventListener("hashchange", () => { showTab(); openRoute(); });
  let openRoute = () => {};
  const SITE = location.href.split("#")[0];
  const shareLink = (hash) => `${SITE}#${hash.split("/").map(encodeURIComponent).join("/")}`;
  function toast(msg) {
    const n = el("div", { class: "toast" }, msg);
    (document.querySelector("dialog[open]") || document.body).append(n); // 열린 창 위에 보이게
    setTimeout(() => n.remove(), 1800);
  }
  async function share(hash, title) {
    const url = shareLink(hash);
    try {
      if (navigator.share) { await navigator.share({ title, url }); return; }
    } catch (e) { if (e.name === "AbortError") return; }
    try { await navigator.clipboard.writeText(url); toast(t("link_copied")); } catch (_) { prompt(t("link_copy"), url); }
  }
  const shareBtn = (fn) => {
    const b = el("button", { class: "share-btn", type: "button", "aria-label": t("share") }, "↗", el("span", { class: "share-l" }, ` ${t("share")}`));
    b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); fn(); });
    return b;
  };

  // ---------- 데이터 ----------
  // 배포 시에는 ./data, 로컬 미리보기(레포 루트에서 서버 실행)에서는 ../data
  let data;
  for (const path of ["data/dashboard.json", "../data/dashboard.json"]) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (r.ok) { data = await r.json(); break; }
    } catch (_) { /* 다음 경로 시도 */ }
  }
  if (!data) { $("updated").textContent = t("load_fail"); return; }
  TR = data.tr || {};

  // ---------- 헤더 ----------
  if (data.debut_date) {
    const days = Math.round((Date.parse(todayKst) - Date.parse(data.debut_date)) / 86400000) + 1;
    $("dday").textContent = `D+${days}`;
    $("debut").textContent = t("debut", { d: data.debut_date.replaceAll("-", ".") });
  }
  $("updated").textContent = data.updated_at ? t("last", { t: data.updated_at.slice(0, 16).replace("T", " ") }) : t("not_yet");
  if (data.feedback_url) { $("feedback").href = data.feedback_url; $("feedback").hidden = false; }

  // ---------- 영상 카드 ----------
  const ymd = (iso) => (iso ? kstFmt.format(new Date(iso)).replaceAll("-", ".") : "");
  // 업로드 3일(72시간) 이내 = NEW, 7일 이내는 'N시간 전/N일 전'
  const NEW_HOURS = 72;
  const ageHours = (iso) => (iso ? (Date.now() - Date.parse(iso)) / 3600000 : Infinity);
  const isNew = (v) => ageHours(v.published_at) <= NEW_HOURS;
  function when(iso) {
    const h = ageHours(iso);
    if (h < 1) return t("just_now");
    if (h < 24) return t("hours_ago", { n: Math.floor(h) });
    if (h < 24 * 7) return t("days_ago", { n: Math.floor(h / 24) });
    return ymd(iso);
  }
  const catLabel = (c) => t(`cat.${c}`);
  // '봤어요': 카드를 눌러 영상을 열면 자동 체크, ✓ 버튼으로 직접 켜고 끄기
  const seen = new Set(pref.get("seen", []));
  const saveSeen = () => pref.set("seen", [...seen].slice(-3000));
  function setSeen(id, on) {
    if (on) seen.add(id); else seen.delete(id);
    saveSeen();
    document.querySelectorAll(`.video[data-id="${CSS.escape(id)}"]`).forEach((c) => c.classList.toggle("seen", on));
  }
  function videoCard(v, chipText, ...extra) {
    const fresh = isNew(v);
    const check = el("button", { class: "seen-btn", type: "button", "aria-label": t("seen") }, "✓");
    check.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); setSeen(v.id, !seen.has(v.id)); });
    const card = el("a", { class: `video${fresh ? " is-new" : ""}${seen.has(v.id) ? " seen" : ""}`, "data-id": v.id,
                           href: ytUrl(v.id), target: "_blank", rel: "noopener" },
      el("div", { class: "thumb" },
        el("img", { src: thumbUrl(v.id), alt: "", loading: "lazy" }),
        fresh ? el("span", { class: "new" }, "NEW") : null,
        v.short ? el("span", { class: "badge" }, t("short")) : null,
        check),
      el("div", { class: "t" }, v.title),
      el("div", { class: "m" }, chipText ? el("span", { class: "chip" }, chipText) : null,
        el("span", { title: ymd(v.published_at), class: fresh ? "when-new" : "" }, when(v.published_at)),
        v.channel ? ` · ${v.channel}` : null),
      el("div", { class: "m" }, t("views", { v: fmt(v.views) }), v.delta ? " · " : null, deltaSpan(v.delta)),
      ...extra,
    );
    card.addEventListener("click", () => setSeen(v.id, true));
    return card;
  }

  // ---------- 한눈에 ----------
  for (const k of data.kpis) {
    const sub = k.key === "mv_total" ? t("kpi.mv_count", { n: k.count })
      : k.key === "fancam_total" ? t("kpi.fancam_count", { n: k.count }) : k.sub;
    $("kpis").append(el("div", { class: "card kpi" },
      el("div", { class: "label" }, k.key ? t(`kpi.${k.key}`) : k.label),
      el("div", { class: "value" }, fmt(k.value)),
      el("div", { class: "sub" }, sub, k.delta ? " · " : null, deltaSpan(k.delta)),
    ));
  }

  function upcomingBirthdays(days = 30) {
    const out = [];
    const today = Date.parse(todayKst);
    const year = +todayKst.slice(0, 4);
    for (const m of data.members || []) {
      if (!/^\d{2}-\d{2}$/.test(m.birthday || "")) continue;
      for (const y of [year, year + 1]) {
        const date = `${y}-${m.birthday}`;
        const diff = Math.round((Date.parse(date) - today) / 86400000);
        if (diff >= 0 && diff <= days) {
          out.push({ date, type: t("ev.birthday"), title: t("birthday_ev", { name: m.name, dd: diff ? `D-${diff}` : "D-DAY" }), member: m.name });
          break;
        }
      }
    }
    return out;
  }
  // 달력 칸에 들어갈 짧은 이름 (음방은 팬들이 부르는 줄임말)
  const SHORT_KO = { 뮤직뱅크: "뮤뱅", 인기가요: "인가", 음악중심: "음중", 엠카운트다운: "엠카", 쇼챔피언: "쇼챔", 더쇼: "더쇼",
    "SHOW K-POP": "쇼K팝", "케이팝업 차트쇼": "케팝업", "KBS 가요대축제": "가요대축제", "SBS 가요대전": "가요대전" };
  const SHORT_EN = { 뮤직뱅크: "MBank", 인기가요: "Inki", 음악중심: "MCore", 엠카운트다운: "MCD", 쇼챔피언: "SChamp", 더쇼: "TheShow",
    "SHOW K-POP": "SKPop", "케이팝업 차트쇼": "KPopUp", "KBS 가요대축제": "KBS SF", "SBS 가요대전": "SBS GD" };
  const short = (show) => (!show ? "" : LANG === "ko" ? SHORT_KO[show] || show : SHORT_EN[show] || tc(show));
  const shortOf = (e) => {
    if (e.short) return tc(e.short);
    if (e.member) return e.member;
    if (e.key === "anniv_days") return `D+${e.n}`;
    if (e.key === "anniv_debut") return "DEBUT";
    if (e.key === "anniv_years") return `${e.n}${LANG === "ko" ? "주년" : "y"}`;
    const m = /^(.+) 출연$/.exec(e.title || "");
    if (m) return short(m[1]);
    return tx(e).replace(/^[^\p{L}\p{N}]+/u, "").slice(0, 8);
  };
  const voteEvents = (data.votes || []).map((v) => ({
    date: v.end.slice(0, 10), time: v.end.slice(11), type: t("votes"),
    title: `🗳 ${[tc(v.show), tc(v.title)].filter(Boolean).join(" ")}`, url: v.url, short: short(v.show) || t("votes"),
  }));
  const supportEvents = (data.supports || []).filter((x) => x.start >= todayKst).map((x) => ({
    date: x.start, type: x.kind, title: `☕ ${[x.member, x.title].filter(Boolean).join(" ")}`, url: x.url,
  }));
  // 일정 구분: 방송(음방·라이브) / 기념일(생일·데뷔 기념일) / 기타(투표 마감·서포트·발매 등)
  const groupOf = (e) => (e.member || e.anniv || e.type === "기념일" ? "anniv"
    : ["음방", "라이브"].includes(e.type) || /출연$/.test(e.title || "") ? "show" : "etc");
  // 시간이 없는 음방 일정은 투표 가이드의 방송 시간(예: '금 17:15 · KBS2')으로 채우기
  const showTime = {};
  for (const v of data.howto?.voting || []) { const m = /(\d{1,2}:\d{2})/.exec(v.when || ""); if (m) showTime[v.show] = m[1]; }
  const prerecEvents = (data.prerecs || []).map((v) => ({
    date: v.start.slice(0, 10), time: v.start.slice(11), type: t("prerec"),
    title: `📝 ${t("prerec_title", { show: tc(v.show) })}`, url: v.url || v.source, short: `${short(v.show)}✍`,
  }));
  // 지난 일정도 달력에 남김 — 목록·개수·'다가오는 일정'은 오늘 이후만 (upcomingEvents)
  const allEvents = [...(data.events || []), ...upcomingBirthdays(), ...voteEvents, ...supportEvents, ...prerecEvents]
    .map((e) => {
      const show = /^(.+) 출연$/.exec(e.title || "")?.[1];
      return { ...e, group: groupOf(e), time: e.time || (show && showTime[show]) || e.time };
    })
    .sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
  const upcomingEvents = allEvents.filter((e) => e.date >= todayKst);
  // 달력에 넣을 생일은 보는 달 기준으로 (목록은 30일 이내만)
  const birthdaysIn = (y, mo) => (data.members || []).filter((m) => (m.birthday || "").startsWith(String(mo).padStart(2, "0") + "-"))
    .map((m) => ({ date: `${y}-${m.birthday}`, type: t("ev.birthday"), title: `🎂 ${t("ev.birthday")} · ${m.name}`, member: m.name, group: "anniv" }));

  const EV_GROUPS = [["all", "ev_all"], ["show", "ev_show_g"], ["anniv", "ev_anniv_g"], ["etc", "ev_etc_g"]];
  let evGroup = pref.get("evGroup", "all");
  let evView = pref.get("evView", "cal");
  const todayD = new Date(`${todayKst}T00:00:00Z`);
  let calY = todayD.getUTCFullYear(), calM = todayD.getUTCMonth() + 1, calSel = todayKst;
  let calFold = pref.get("calFold", true);
  const evTabs = el("div", { class: "filter-row ev-tabs" });
  const viewBtn = el("button", { type: "button", class: "ev-view" });
  const calBox = el("div", { class: "cal" });
  const pass = (e) => evGroup === "all" || e.group === evGroup;

  function evItem(e) {
    const d = new Date(`${e.date}T00:00:00Z`);
    const wd = t("weekdays");
    const isToday = e.date === todayKst;
    const whenEl = el("div", { class: "when" },
      isToday ? el("span", { class: "today" }, t("today")) : el("b", {}, `${d.getUTCMonth() + 1}.${d.getUTCDate()}`),
      ` (${wd[d.getUTCDay()]})`, e.time ? ` ${e.time}` : null,
      e.time && localOf(e.date, e.time) ? el("span", { class: "local-t" }, localOf(e.date, e.time)) : null);
    let title;
    if (e.member) {
      title = el("button", { type: "button", class: "linklike" }, e.title);
      const mem = data.members.find((x) => x.name === e.member);
      title.addEventListener("click", () => openMember(mem));
    } else {
      title = e.url ? ext(e.url, tx(e)) : el("span", {}, tx(e));
    }
    title.classList.add("what");
    const live = e.type === "음방" && e.date >= todayKst ? liveLink(e.title) : null;
    return el("li", { class: `ev-${e.group}` }, whenEl, el("div", {}, e.type ? el("span", { class: "chip" }, tc(e.type)) : null, title, live));
  }

  function monthEvents(y, mo) {
    const pre = `${y}-${String(mo).padStart(2, "0")}`;
    const seenB = new Set(allEvents.filter((e) => e.member).map((e) => e.date + e.member));
    return [...allEvents.filter((e) => e.date.startsWith(pre)),
      ...birthdaysIn(y, mo).filter((b) => !seenB.has(b.date + b.member))].filter(pass);
  }

  function renderCal() {
    const evs = monthEvents(calY, calM);
    const byDay = {};
    for (const e of evs) (byDay[e.date] ||= []).push(e);
    const first = new Date(Date.UTC(calY, calM - 1, 1));
    const days = new Date(Date.UTC(calY, calM, 0)).getUTCDate();
    const prev = el("button", { type: "button", class: "cal-nav", "aria-label": "‹" }, "‹");
    const next = el("button", { type: "button", class: "cal-nav", "aria-label": "›" }, "›");
    prev.addEventListener("click", () => { calM -= 1; if (calM < 1) { calM = 12; calY -= 1; } calSel = ""; renderCal(); });
    next.addEventListener("click", () => { calM += 1; if (calM > 12) { calM = 1; calY += 1; } calSel = ""; renderCal(); });
    const monthName = new Intl.DateTimeFormat(LOCALES[LANG], { year: "numeric", month: "long", timeZone: "UTC" }).format(first);
    const grid = el("div", { class: "cal-grid" }, ...t("weekdays").map((w, i) => el("div", { class: `cal-wd${i === 0 ? " sun" : i === 6 ? " sat" : ""}` }, w)));
    // 접힌 상태(이번 달·기본 보기)는 오늘이 있는 주부터 2주만
    const thisMonth = calY === todayD.getUTCFullYear() && calM === todayD.getUTCMonth() + 1;
    const folded = calFold && thisMonth;
    const lead = first.getUTCDay();
    const weekOf = (d) => Math.floor((lead + d - 1) / 7);
    const showWeeks = folded ? [weekOf(todayD.getUTCDate()), weekOf(todayD.getUTCDate()) + 1] : null;
    const visible = (d) => !showWeeks || showWeeks.includes(weekOf(d));
    if (!folded) for (let i = 0; i < lead; i++) grid.append(el("div", { class: "cal-cell empty" }));
    else for (let i = 0; i < lead && showWeeks[0] === 0; i++) grid.append(el("div", { class: "cal-cell empty" }));
    for (let d = 1; d <= days; d++) {
      if (!visible(d)) continue;
      const iso = `${calY}-${String(calM).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const list = byDay[iso] || [];
      const groups = [...new Set(list.map((e) => e.group))];
      const cell = el("button", { type: "button", class: `cal-cell${iso === todayKst ? " is-today" : ""}${iso === calSel ? " is-sel" : ""}${iso < todayKst ? " past" : ""}`,
        "aria-label": `${iso} ${list.length}` },
        el("span", { class: "cal-d" }, String(d)),
        el("span", { class: "cal-evs" }, ...list.slice(0, 2).map((e) => el("span", { class: `cal-ev ev-${e.group}` }, shortOf(e))),
          list.length > 2 ? el("span", { class: "cal-more" }, `+${list.length - 2}`) : null));
      cell.addEventListener("click", () => { calSel = iso; renderCal(); });
      grid.append(cell);
    }
    // 고른 날 일정, 없으면 이 달 남은 일정 (지난 달이면 그 달 일정 전체)
    const sel = calSel ? (byDay[calSel] || []) : [];
    const pastMonth = `${calY}-${String(calM).padStart(2, "0")}` < todayKst.slice(0, 7);
    const rest = evs.filter((e) => pastMonth || e.date >= (calSel || todayKst)).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
    const list = calSel && sel.length ? sel : rest.slice(0, 6);
    const foldBtn = thisMonth ? el("button", { type: "button", class: "cal-fold" }, calFold ? `${t("cal_more")} ▾` : `${t("cal_less")} ▴`) : null;
    foldBtn?.addEventListener("click", () => { calFold = !calFold; pref.set("calFold", calFold); renderCal(); });
    calBox.replaceChildren(
      ...[el("div", { class: "cal-head" }, prev, el("b", {}, monthName), next),
        grid, foldBtn].filter(Boolean),
      el("div", { class: "cal-sub muted small" }, (calSel && sel.length) || pastMonth ? "" : t("cal_upcoming")),
      el("ul", { class: "events" }, ...(list.length ? list.map(evItem) : [el("li", { class: "empty" }, "–")])));
  }

  function renderEvents() {
    evTabs.replaceChildren(...EV_GROUPS.filter(([k]) => k === "all" || allEvents.some((e) => e.group === k)).map(([k, label]) => {
      const n = k === "all" ? upcomingEvents.length : upcomingEvents.filter((e) => e.group === k).length;
      const b = el("button", { type: "button", class: k === evGroup ? "on" : "" }, `${t(label)} ${n}`);
      b.addEventListener("click", () => { evGroup = k; pref.set("evGroup", k); renderEvents(); });
      return b;
    }));
    viewBtn.textContent = evView === "cal" ? `☰ ${t("ev_list")}` : `📅 ${t("ev_cal")}`;
    if (evView === "cal") {
      $("events").hidden = true; calBox.hidden = false; renderCal();
    } else {
      calBox.hidden = true; $("events").hidden = false;
      const list = upcomingEvents.filter(pass).slice(0, 10);
      $("events").replaceChildren(...(list.length ? list.map(evItem) : [el("li", { class: "empty" }, "–")]));
    }
  }
  viewBtn.addEventListener("click", () => { evView = evView === "cal" ? "list" : "cal"; pref.set("evView", evView); renderEvents(); });
  if (evGroup !== "all" && !allEvents.some((e) => e.group === evGroup)) evGroup = "all";
  const evHead = $("eventsSection").querySelector(".sec-head");
  evHead.insertBefore(viewBtn, evHead.querySelector(".see-all"));
  $("events").before(evTabs);
  $("events").after(calBox);
  renderEvents();

  const newCount = data.videos.filter(isNew).length;
  if (newCount) $("recentHead").append(el("span", { class: "new-count" }, `NEW ${newCount}`));
  if (data.recent.length) {
    for (const v of data.recent) $("recent").append(videoCard(v, v.member || catLabel(v.category)));
    if (MOBILE) fold($("recent"), 6);
  } else {
    $("recent").replaceWith(empty(t("empty_videos")));
  }

  // ---------- 응원 ----------
  function duration(ms) {
    const m = Math.max(0, Math.floor(ms / 60000));
    if (m >= 1440) return t("dur_d", { n: Math.floor(m / 1440) }) + " " + t("dur_h", { n: Math.floor((m % 1440) / 60) });
    if (m >= 60) return t("dur_h", { n: Math.floor(m / 60) }) + " " + t("dur_m", { n: m % 60 });
    return t("dur_m", { n: m });
  }
  const prerecs = (data.prerecs || []).filter((v) => kstDate(v.end) > Date.now());
  if (prerecs.length) {
    for (const v of prerecs) {
      const start = kstDate(v.start), end = kstDate(v.end);
      const open = Date.now() >= start;
      const urgent = !open && start - Date.now() < 3 * 3600000;
      $("prerecs").append(el("div", { class: `vote${open || urgent ? " urgent" : ""}` },
        el("div", { class: "vote-top" },
          el("span", { class: `chip ${open ? "chip-on" : ""}` }, open ? t("vote_now") : t("vote_soon")),
          el("b", {}, t("prerec_title", { show: tc(v.show) })),
          v.record ? el("span", { class: "muted" }, ` · ${t("prerec_rec", { d: v.record.slice(5).replace("-", ".") })}`) : null),
        el("div", { class: "vote-time" }, open ? t("vote_ends", { t: duration(end - Date.now()) }) : t("vote_starts", { t: duration(start - Date.now()) }),
          el("span", { class: "muted" }, ` · ${v.start.slice(5).replace("-", ".")} ~ ${v.end.slice(11)}`)),
        el("div", { class: "vote-links" }, v.url ? ext(v.url, t("prerec_go")) : null,
          v.source ? ext(v.source, t("from_notice"), " ↗") : null)));
    }
  } else {
    $("prerecSec").remove();
  }

  const votes = (data.votes || []).filter((v) => kstDate(v.end) > Date.now());
  // 투표 링크가 없으면 앱 이름으로 찾기 (공식 링크가 생기면 votes.yml url에)
  const appSearch = (app) => {
    const name = (String(app).match(/\(([^)]+)\)/) || [])[1] || String(app);  // '유픽(U+PICK)' → 'U+PICK'
    return `https://www.google.com/search?q=${encodeURIComponent(`${name} app`)}`;
  };
  // 투표 타일: 앱 로고(글자)·제목·남은 시간 크게·진행 막대 — 한눈에(간단히)·응원 탭(설명까지)
  const APP_COLORS = { "하이어": "#ff2d78", "빅크": "#16161d", "유픽": "#6c4cf5", "뮤니버스": "#0ea5e9", "케이탑스타": "#f59e0b", "마이원픽": "#10b981", "아이돌챔프": "#e11d48", "엠넷플러스": "#111827" };
  const appColor = (app) => {
    const k = Object.keys(APP_COLORS).find((x) => String(app).includes(x));
    if (k) return APP_COLORS[k];
    let h = 0;
    for (const c of String(app)) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h} 55% 45%)`;
  };
  const appLetter = (app) => ((String(app).match(/\(([A-Za-z])/) || [])[1] || String(app).trim()[0] || "?").toUpperCase();
  const SHOW_RX = /더쇼|THE SHOW|쇼챔|엠카|M COUNTDOWN|뮤직뱅크|뮤뱅|음악중심|음중|인기가요|SHOW K-POP|케이팝업/i;
  // 투표 앱 스토어 링크 (info.yml vote_apps) — 아이폰은 App Store, 그 밖엔 Google Play (설치돼 있으면 '열기')
  const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const appStore = (app) => {
    const x = (data.info?.vote_apps || []).find((a) => String(app || "").includes(a.name));
    return x ? (IOS ? x.ios : x.android) || x.ios || x.android : null;
  };
  // 투표 버튼이 갈 곳: 투표는 앱 안에서 하니 앱(스토어, 설치돼 있으면 '열기')이 먼저, 앱을 모르면 투표 링크 → 앱 검색
  const voteHref = (v) => appStore(v.app) || v.url || (v.app ? appSearch(v.app) : "");
  const voteLabel = (v) => (voteHref(v) === appStore(v.app) ? t("vote_in_app", { app: tc(v.app) }) : v.url ? t("vote_open") : t("vote_find_app", { app: tc(v.app) }));
  const voteTile = (v, full) => {
    const start = kstDate(v.start), end = kstDate(v.end), now = Date.now();
    const open = now >= start;
    const urgent = open && end - now < 72 * 3600000;
    const href = voteHref(v);
    const pct = open ? Math.min(100, Math.max(3, ((now - start) / Math.max(1, end - start)) * 100)) : 0;
    const title = [v.show && !String(v.title).includes(v.show) ? tc(v.show) : "", tc(v.title)].filter(Boolean).join(" · ");
    const tile = el(href ? "a" : "div", { class: `vt${urgent ? " urgent" : ""}${open ? "" : " upcoming"}`, ...(href ? { href, target: "_blank", rel: "noopener" } : {}) },
      el("span", { class: `vt-st${urgent ? " soon" : open ? "" : " up"}` }, urgent ? t("vote_urgent") : open ? t("vote_now") : t("vote_soon")),
      el("div", { class: "vt-app" }, el("span", { class: "vt-lg", style: `background:${appColor(v.app || v.show)}` }, appLetter(v.app || v.show)),
        el("span", {}, [tc(v.app || ""), v.show && SHOW_RX.test(v.show) ? tc(v.show) : ""].filter(Boolean).join(" · ")),
        v.fan ? el("span", { class: "chip chip-fan", title: t("vote_fan_tip") }, t("vote_fan")) : null),
      el("div", { class: "vt-t" }, title),
      el("div", { class: "vt-cd" }, open ? t("vote_left", { t: duration(end - now) }) : t("vote_to_start", { t: duration(start - now) })),
      open ? el("div", { class: "vt-bar" }, el("i", { style: `width:${pct.toFixed(0)}%` })) : null,
      el("div", { class: "vt-when muted" }, open ? t("vote_end_at", { t: v.end.slice(5).replace("-", ".") }) : `${v.start.slice(5).replace("-", ".")} ~ ${v.end.slice(v.end.slice(0, 10) === v.start.slice(0, 10) ? 11 : 5).replace("-", ".")}`,
        localOf(v.end.slice(0, 10), v.end.slice(11)) ? el("span", { class: "local-t" }, localOf(v.end.slice(0, 10), v.end.slice(11))) : null),
      full && v.note ? el("div", { class: "vt-note" }, tc(v.note)) : null,
      el("div", { class: "vt-go" }, href ? voteLabel(v) : ""));
    // 응원 탭: 앱으로 가는 타일엔 투표 안내 글 링크도 따로 (타일 밖 한 줄)
    if (full && v.url && href !== v.url) return el("div", { class: "vt-wrap" }, tile, ext(v.url, `↗ ${t("from_notice")}`));
    return tile;
  };
  const voteKey = (v) => (Date.now() >= kstDate(v.start) ? kstDate(v.end) : kstDate(v.start));
  // 상단 띠: 진행 중이고 48시간 안에 마감하는 투표 (닫으면 그 투표는 이 기기에서 다시 안 보임)
  {
    const hidden = new Set(pref.get("voteBarHidden", []));
    const soon = votes.filter((v) => Date.now() >= kstDate(v.start) && kstDate(v.end) - Date.now() < 48 * 3600000 && !hidden.has(v.end + v.title))
      .sort((a, b) => kstDate(a.end) - kstDate(b.end));
    if (soon.length) {
      const v = soon[0];
      const close = el("button", { type: "button", class: "vb-x", "aria-label": "✕" }, "✕");
      const bar = el("div", { class: `vote-bar${kstDate(v.end) - Date.now() < 6 * 3600000 ? " urgent" : ""}`, role: "status" },
        // 누르면 바로 투표 링크로 (없으면 투표 앱 찾기)
        el("a", { href: voteHref(v) || "#cheer", ...(voteHref(v) ? { target: "_blank", rel: "noopener" } : {}), class: "vb-main" },
          `🗳 ${[tc(v.show), tc(v.title)].filter(Boolean).join(" · ")} — ${t("vote_ends", { t: duration(kstDate(v.end) - Date.now()) })}`,
          soon.length > 1 ? el("span", { class: "vb-more" }, ` +${soon.length - 1}`) : null),
        voteHref(v) ? el("a", { class: "vb-go", href: voteHref(v), target: "_blank", rel: "noopener" }, voteLabel(v)) : null, close);
      close.addEventListener("click", () => { hidden.add(v.end + v.title); pref.set("voteBarHidden", [...hidden].slice(-30)); bar.remove(); });
      $("tabs").before(bar);
    }
  }
  // 음방 1위 축하 배너: 1위 후 7일 동안 맨 위에 크게 (첫 1위면 '데뷔 첫 음방 1위')
  {
    const wins = (data.timeline || []).filter((x) => x.kind === "win").sort((a, b) => a.date.localeCompare(b.date));
    const w = wins[wins.length - 1];
    if (w && (Date.parse(todayKst) - Date.parse(w.date)) / 86400000 <= 7) {
      const first = wins.length === 1;
      const n = data.debut_date ? Math.round((Date.parse(w.date) - Date.parse(data.debut_date)) / 86400000) : 0;
      const show = tc(w.show);
      // 주소 끝에 ?win=날짜 — 카톡 등이 예전 미리보기를 저장해 둬도 새 카드로 다시 읽게
      const site = `${location.origin}${location.pathname}?win=${w.date.replaceAll("-", "")}`;
      const shareText = [t("win_share_text", { show }), w.tags].filter(Boolean).join(" ");
      const share = el("button", { type: "button", class: "win-btn" }, t("win_share"));
      // 폰: 공유 시트(카톡 등) / PC: X에 올리기 · 링크 복사 메뉴 (PC 공유 시트엔 X·카톡이 없어서)
      const TOUCH = window.matchMedia("(pointer: coarse)").matches;
      const xUrl = `https://x.com/intent/post?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(site)}`;
      const menu = el("div", { class: "win-menu", hidden: "" },
        el("a", { href: xUrl, target: "_blank", rel: "noopener" }, t("win_share_x")),
        el("button", { type: "button" }, t("win_share_copy")));
      menu.querySelector("button").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(`${shareText}\n${site}`); toast(t("link_copied")); } catch (_) { prompt(t("link_copy"), `${shareText}\n${site}`); }
        menu.hidden = true;
      });
      share.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (TOUCH && navigator.share) { try { await navigator.share({ text: `${shareText}\n${site}` }); } catch (_) { /* 취소 */ } return; }
        menu.hidden = !menu.hidden;
      });
      document.addEventListener("click", (e) => { if (!menu.contains(e.target)) menu.hidden = true; });
      const watch = w.url || `https://www.youtube.com/results?search_query=${encodeURIComponent(`A2O SOUL ${w.show} 1위 앵콜`)}`;
      // 공식 단체 사진 (info.yml wins.image) — 못 불러오면 사진 없이
      let photo = null;
      if (w.image) {
        const img = el("img", { src: w.image, alt: "A2O SOUL", referrerpolicy: "no-referrer", decoding: "async" });
        photo = w.image_post ? el("a", { class: "win-photo", href: w.image_post, target: "_blank", rel: "noopener" }, img) : el("div", { class: "win-photo" }, img);
        img.addEventListener("error", () => { photo.remove(); banner.classList.remove("has-photo"); });
      }
      const banner = el("section", { class: `win-hero${photo ? " has-photo" : ""}`, role: "status" },
        photo,
        el("div", { class: "win-confetti", "aria-hidden": "true" }, ...Array.from({ length: 28 }, (_, i) => el("i", { style: `--i:${i}` }))),
        el("div", { class: "win-trophy", "aria-hidden": "true" }, "🏆"),
        el("div", { class: "win-body" },
          el("div", { class: "win-kicker" }, "A2O SOUL"),
          el("h2", { class: "win-title" }, first ? t("win_first", { show }) : t("win_n", { show })),
          el("div", { class: "win-sub" }, [`${show}${w.ep ? ` ${t("win_ep", { n: w.ep })}` : ""}`, w.date.replaceAll("-", "."), n > 0 ? t("win_days", { n }) : ""].filter(Boolean).join(" · ")),
          el("div", { class: "win-acts" }, el("a", { class: "win-btn primary", href: watch, target: "_blank", rel: "noopener" }, t("win_watch")),
            el("span", { class: "win-share" }, share, menu))));
      $("tabs").before(banner);
    }
  }
  // 상단 띠: 오늘 A2O SOUL이 나오는 음방 — 시작 1시간 반 전부터 끝날 무렵까지 '생방송 보기'
  {
    const nowMs = Date.now();
    // 일정에 시간이 없으면 투표 가이드(howto.yml)의 방송 시간으로 ('화 18:00')
    const airTime = (e) => e.time || (/(\d{1,2}:\d{2})/.exec(((data.howto?.voting || []).find((v) => liveFor(e.title)?.show && String(v.show).includes(liveFor(e.title).show)) || {}).when || "") || [])[1];
    const onAir = (data.events || []).filter((e) => e.type === "음방" && e.date === todayKst && liveFor(e.title) && airTime(e))
      .map((e) => ({ e: { ...e, time: airTime(e).padStart(5, "0") }, at: +kstDate(`${e.date} ${airTime(e).padStart(5, "0")}`) }))
      .find(({ at }) => nowMs >= at - 90 * 60000 && nowMs <= at + 75 * 60000);
    if (onAir) {
      const x = liveFor(onAir.e.title);
      const now = nowMs >= onAir.at;
      $("tabs").before(el("a", { class: `vote-bar live-bar${now ? " urgent" : ""}`, href: x.url, target: "_blank", rel: "noopener", role: "status" },
        el("span", { class: "vb-main" }, now ? t("live_now", { show: tc(x.show) }) : t("live_today", { t: onAir.e.time, show: tc(x.show) })),
        el("span", { class: "vb-go" }, `${x.label} ↗`)));
    }
  }
  // 이번 주 음방 체크리스트 — 월~일, 방송 요일·시간·투표 앱, 지난 날은 흐리게, 오늘은 강조
  {
    const DAYS = "월화수목금토일";
    const base = new Date(`${todayKst}T00:00:00Z`); // 날짜 계산만 하려고 UTC 자정으로
    const dow = (base.getUTCDay() + 6) % 7; // 월=0
    const ymd = (d) => new Date(+base + (d - dow) * 864e5).toISOString().slice(0, 10);
    const fmtDay = new Intl.DateTimeFormat(LANG === "zh" ? "zh-CN" : LANG, { weekday: "short", timeZone: "UTC" });
    const rows = (data.howto?.voting || []).map((v) => {
      const d = DAYS.indexOf(String(v.when || "").trim()[0]);
      if (d < 0) return null;
      const date = ymd(d), time = (/(\d{1,2}:\d{2})/.exec(v.when) || [])[1] || "";
      const show = String(v.show), live = liveFor(show);
      const on = (data.events || []).some((e) => e.type === "음방" && e.date === date && String(e.title).includes(show));
      const open = votes.filter((x) => `${x.show} ${x.title}`.includes(show) && Date.now() < kstDate(x.end.includes(" ") ? x.end : `${x.end} 23:59`));
      const state = date < todayKst ? "past" : date === todayKst ? "today" : "next";
      return { d, date, time, show, v, live, on, open, state };
    }).filter(Boolean).sort((a, b) => a.d - b.d);
    if (rows.length) {
      const box = el("div", { class: "wk" },
        el("div", { class: "wk-head" }, el("b", {}, t("wk_title")), el("span", { class: "muted small" }, `${ymd(0).slice(5).replace("-", ".")} ~ ${ymd(6).slice(5).replace("-", ".")}`)),
        ...rows.map((r) => el("div", { class: `wk-row ${r.state}` },
          el("div", { class: "wk-day" }, el("b", {}, fmtDay.format(new Date(`${r.date}T00:00:00Z`))), el("span", {}, r.date.slice(5).replace("-", "."))),
          el("div", { class: "wk-body" },
            el("div", {}, el("b", {}, tc(r.show)), r.time ? el("span", { class: "muted small" }, ` ${r.time}`) : null,
              r.state === "today" ? el("span", { class: "chip chip-on" }, t("wk_today")) : null,
              r.on ? el("span", { class: "chip wk-on" }, t("wk_on")) : null,
              r.state === "past" ? el("span", { class: "muted small" }, ` · ${t("wk_past")}`) : null),
            el("div", { class: "muted small" }, [r.v.pre ? `${t("wk_pre")} ${tc(r.v.pre)}` : "", r.v.live ? `${t("wk_live")} ${tc(r.v.live)}` : ""].filter(Boolean).join(" · ")),
            ...r.open.map((x) => el("div", { class: "small wk-vote" }, `🗳 ${tc(x.title)} · ${t("wk_until", { t: x.end.slice(5).replace("-", ".") })}`))),
          r.state !== "past" && r.live ? ext(r.live.url, `${r.live.label} ↗`) : null)));
      $("votes").parentNode.insertBefore(box, $("votes"));
    }
  }
  if (votes.length) {
    const sorted = [...votes].sort((a, b) => voteKey(a) - voteKey(b));
    const groups = [["", t("ev_all"), () => true],
      ["open", t("vote_now"), (v) => Date.now() >= kstDate(v.start)],
      ["soon", t("vote_soon"), (v) => Date.now() < kstDate(v.start)],
      ["show", t("vote_f_show"), (v) => SHOW_RX.test(`${v.show} ${v.title}`)],
      ["app", t("vote_f_app"), (v) => !SHOW_RX.test(`${v.show} ${v.title}`)]]
      .map(([k, label, f]) => [k, label, f, sorted.filter(f).length]).filter(([k, , , n]) => !k || (n && n < sorted.length));
    let gk = "";
    const seg = el("div", { class: "filter-row era-row vt-seg" });
    const drawVotes = () => {
      seg.replaceChildren(...groups.map(([k, label, , n]) => {
        const b = el("button", { type: "button", class: k === gk ? "on" : "", "aria-pressed": String(k === gk) }, `${label} ${n}`);
        b.addEventListener("click", () => { gk = k; drawVotes(); });
        return b;
      }));
      const f = groups.find((g) => g[0] === gk)[2];
      $("votes").replaceChildren(...sorted.filter(f).map((v) => voteTile(v, true)));
    };
    if (groups.length > 2) $("votes").before(seg);
    drawVotes();
    // 한눈에 탭 맨 위: 마감 가까운 순 타일 (폰은 가로로 넘기기)
    $("voteHomeList").replaceChildren(...sorted.map((v) => voteTile(v, false)));
    $("voteHomeCount").textContent = t("vote_count", { n: sorted.length });
    $("voteHome").hidden = false;
  } else {
    $("votes").append(empty(t("no_votes")));
    $("voteHome").remove();
  }

  // 에투소 스밍 리스트 — 원클릭 담기(앱 링크) + 곡별 검색 링크
  const sp = data.stream_playlist || {};
  if ((sp.tracks || []).length) {
    const q = (song) => encodeURIComponent(`A2O SOUL ${song}`);
    const ko = LANG === "ko";
    const kr = [[ko ? "멜론" : "Melon", (x) => `https://www.melon.com/search/total/index.htm?q=${q(x)}`], [ko ? "지니" : "Genie", (x) => `https://www.genie.co.kr/search/searchMain?query=${q(x)}`],
      [ko ? "벅스" : "Bugs", (x) => `https://music.bugs.co.kr/search/integrated?q=${q(x)}`], ["FLO", (x) => `https://www.music-flo.com/search/all?keyword=${q(x)}`]];
    const global = [["Spotify", (x) => `https://open.spotify.com/search/${q(x)}`], ["YouTube Music", (x) => `https://music.youtube.com/search?q=${q(x)}`]];
    const sites = ko ? [...kr, ...global] : [...global, ...kr];
    const secs = (t) => { const m = /^(\d+):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : 0; };
    // 리스트 이미지 — 캔버스로 그려서 저장·공유 가능하게 (4:5)
    const listImg = () => {
      const W = 1080, H = 1350, c = document.createElement("canvas");
      c.width = W; c.height = H;
      const x = c.getContext("2d"), F = getComputedStyle(document.body).fontFamily;
      const bg = x.createLinearGradient(0, 0, W, H);
      bg.addColorStop(0, "#efeaff"); bg.addColorStop(1, "#ffe9f3");
      x.fillStyle = bg; x.fillRect(0, 0, W, H);
      x.fillStyle = "#6c4cf5"; x.font = `700 34px ${F}`; x.fillText("A2O SOUL", 90, 140);
      x.fillStyle = "#16161d"; x.font = `800 72px ${F}`; x.fillText(ko ? "에투소 스밍 리스트" : "Streaming playlist", 90, 230);
      const top = 320, rowH = (H - top - 170) / sp.tracks.length;
      sp.tracks.forEach((t2, i) => {
        const y = top + i * rowH;
        x.fillStyle = "rgba(255,255,255,.75)";
        x.beginPath(); x.roundRect(80, y + 8, W - 160, rowH - 16, 24); x.fill();
        x.fillStyle = t2.title ? "#6c4cf5" : "#9a9aab"; x.font = `800 40px ${F}`; x.textAlign = "center";
        x.fillText(String(i + 1), 150, y + rowH / 2 + 14); x.textAlign = "left";
        x.fillStyle = "#16161d"; x.font = `${t2.title ? 800 : 600} 44px ${F}`; x.fillText(t2.song, 210, y + rowH / 2 + 15);
        if (t2.time) { x.fillStyle = "#6b6b7b"; x.font = `500 32px ${F}`; x.textAlign = "right"; x.fillText(t2.time, W - 120, y + rowH / 2 + 12); x.textAlign = "left"; }
      });
      x.fillStyle = "#6b6b7b"; x.font = `500 30px ${F}`;
      x.fillText(ko ? "↻ 전체 반복 · 셔플 끄기 · 중복 곡 허용" : "↻ Repeat all · Shuffle off · Allow duplicates", 90, H - 90);
      x.textAlign = "right"; x.fillText("a2osoul-tracker.com", W - 90, H - 90);
      return c.toDataURL("image/png");
    };
    const uniq = [...new Map(sp.tracks.map((x) => [x.song, x])).values()];
    const songLinks = el("details", { class: "howto pl-find" }, el("summary", {}, t("oc_find")),
      el("ul", { class: "howto-steps" }, ...uniq.map((x) => el("li", {}, el("b", {}, x.song), " ",
        el("span", { class: "links small" }, ...sites.map(([label, url]) => ext(url(x.song), label)))))));
    const total = sp.tracks.every((x) => secs(x.time)) ? sp.tracks.reduce((n, x) => n + secs(x.time), 0) : 0;

    // 원클릭 담기 — 기기별 앱 링크 (sming-maker 방식). 멜론은 한 번에 같은 곡을 못 담아서 중복이 나오면 나눠 담기
    const ua = navigator.userAgent;
    const dev = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) ? "ios"
      : /Android/.test(ua) ? "android" : /Mac/.test(navigator.platform || ua) ? "mac" : "win";
    const mobile = dev === "ios" || dev === "android";
    const ids = (p) => sp.tracks.map((x) => (x.ids || {})[p]).filter(Boolean);
    const melonParts = [];
    for (const id of ids("melon")) {
      const cur = melonParts[melonParts.length - 1];
      if (!cur || cur.includes(id)) melonParts.push([id]); else cur.push(id);
    }
    const melonUrl = (l) => (dev === "win" ? `melonapp://play?cType=1&cList=${l}` : dev === "mac" ? `melonplayer://play?menuid=0&cflag=1&cid=${l}` : `melonapp://play?menuid=0&ctype=1&cid=${l}`);
    const g = ids("genie"), bg = ids("bugs"), fl = ids("flo");
    const btn = (href, label, cls = "") => el("a", { class: `oc-btn ${cls}`, href, ...(/^https?:/.test(href) ? { target: "_blank", rel: "noopener" } : {}) }, label);
    const oneClick = [];
    if (melonParts.length) {
      oneClick.push(el("div", { class: "oc-row" }, el("b", { class: "oc-name melon" }, ko ? "멜론" : "Melon"),
        ...melonParts.map((l, i) => {
          const a = btn(melonUrl(l.join(",")), melonParts.length > 1 ? `${i + 1}${ko ? "차" : ""} (${l.length}${ko ? "곡" : ""})` : t("oc_add"));
          a.addEventListener("click", () => a.classList.add("done"));
          return a;
        })));
    }
    if (g.length) oneClick.push(el("div", { class: "oc-row" }, el("b", { class: "oc-name genie" }, ko ? "지니" : "Genie"),
      btn(dev === "ios" ? `ktolleh00167://landing/?landing_type=31&landing_target=${g.join(";")};` : dev === "android" ? `cromegenie://scan/?landing_type=31&landing_target=${g.join(";")};`
        : `https://www.genie.co.kr/player/shareProcessV2?xgnm=${g.join(";")}`, t("oc_add"))));
    if (bg.length) oneClick.push(el("div", { class: "oc-row" }, el("b", { class: "oc-name bugs" }, ko ? "벅스" : "Bugs"),
      btn(mobile ? `bugs3://app/tracks/lists?title=${encodeURIComponent("에투소 스밍")}&miniplay=y&track_ids=${bg.join("|")}|` : `https://music.bugs.co.kr/newPlayer?trackId=${bg.join(",")}`, t("oc_add"))));
    if (fl.length) oneClick.push(el("div", { class: "oc-row" }, el("b", { class: "oc-name flo" }, "FLO"),
      mobile ? btn(`flomobile://play?trackId=${fl.join(",")}`, t("oc_add")) : el("span", { class: "muted small" }, t("oc_mobile_only"))));

    $("streaming").before(el("div", { class: "playlist" },
      el("h3", {}, tc(sp.title)), sp.desc ? el("p", { class: "muted small" }, tc(sp.desc)) : null,
      el("div", { class: "pl-grid" },
      oneClick.length ? el("div", { class: "oneclick" },
        el("div", { class: "oc-head" }, el("b", {}, t("oc_title")),
          el("span", { class: "muted small" }, t("oc_info", { n: sp.tracks.length }) + (total ? ` · ${Math.floor(total / 60)}${ko ? "분" : " min"}` : ""))),
        ...oneClick,
        melonParts.length > 1 ? el("p", { class: "muted small oc-note" }, t("oc_melon_parts", { n: melonParts.length })) : null) : null,
      (() => { const src = listImg(); return el("figure", { class: "pl-img" }, el("img", { src, alt: sp.tracks.map((x, i) => `${i + 1}. ${x.song}`).join(" / ") }),
        el("a", { class: "share-btn", href: src, download: "a2osoul-streaming-list.png" }, t("oc_save"))); })(),
      songLinks,
      (sp.tips || []).length ? el("details", { class: "howto", ...(MOBILE ? {} : { open: "" }) }, el("summary", {}, t("stream_tips")),
        el("ul", { class: "howto-steps" }, ...sp.tips.map((x) => el("li", {}, tc(x))))) : null)));
  }
  if ((data.streaming || []).length) {
    $("streaming").before(el("h3", { class: "pl-mv" }, t("stream_mv")));
    for (const s of data.streaming) {
      $("streaming").append(el("li", {},
        el("div", {}, el("b", {}, s.title), s.note ? el("span", { class: "muted" }, ` · ${tc(s.note)}`) : null),
        Object.keys(s.links).length ? el("div", { class: "links small" }, ...Object.entries(s.links).map(([k, u]) => ext(u, k))) : null));
    }
    fold($("streaming"), MOBILE ? 4 : 8);
  } else if (!(sp.tracks || []).length) {
    $("streaming").closest("section").remove();
  }

  const howto = data.howto || {};
  // '뮤니버스(MUNIVERSE) · 뮤빗(MUBEAT, 글로벌)' → 앱마다 찾기 링크
  const appLinks = (txt) => {
    const raw = String(txt).split(/\s*·\s*/), shown = String(tc(txt)).split(/\s*·\s*/);
    const label = shown.length === raw.length ? shown : raw.map((a) => tc(a));
    return raw.flatMap((a, i) => [i ? " · " : null, ext(appStore(a) || appSearch(a.replace(/,.*\)/, ")")), label[i])]).filter(Boolean);
  };
  if ((howto.voting || []).length || (howto.streaming || []).length) {
    // ① 이번 주 음방 투표: 요일 칸(짧게) + 누른 방송의 앱·메모는 아래 한 줄로
    const DAYS = "월화수목금토일";
    const voting = (howto.voting || []).map((v) => ({ ...v, wd: DAYS.indexOf((v.when || "").trim()[0]) })).filter((v) => v.wd >= 0)
      .sort((a, b) => a.wd - b.wd);
    if (voting.length) {
      const todayWd = (kstDate(todayKst).getUTCDay() + 6) % 7; // 월=0
      const wdName = (i) => new Date(Date.UTC(2026, 10, 16 + i)).toLocaleDateString(LOCALES[LANG] || "en", { weekday: "short", timeZone: "UTC" });
      const nowStr = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date());
      const live = (show) => (data.votes || []).some((x) => x.show === show && (x.start || x.end) <= nowStr && nowStr <= x.end);
      const pick = voting.find((v) => v.wd >= todayWd) || voting[0];
      const detail = el("div", { class: "wk-detail" });
      const showDetail = (v) => {
        detail.replaceChildren(...[
          el("div", {}, el("b", {}, tc(v.show)), v.when ? el("span", { class: "muted" }, ` · ${tc(v.when)}`) : null),
          el("div", { class: "howto-apps" },
            v.pre ? el("span", {}, el("span", { class: "chip" }, t("howto_pre")), " ", ...appLinks(v.pre)) : null,
            v.live ? el("span", {}, el("span", { class: "chip chip-on" }, t("howto_live")), " ", ...appLinks(v.live)) : null),
          v.note ? el("div", { class: "muted small" }, tc(v.note)) : null,
          liveLink(v.show),
          v.url ? ext(v.url, "↗ link") : null].filter(Boolean));
        grid.querySelectorAll(".wk-day").forEach((d) => d.classList.toggle("picked", d.dataset.show === v.show));
      };
      const grid = el("div", { class: "wk-grid", style: `grid-template-columns:repeat(${voting.length},1fr)` }, ...voting.map((v) => {
        const time = (/(\d{1,2}:\d{2})/.exec(v.when || "") || [])[1] || "";
        const b = el("button", { type: "button", class: `wk-day${v.wd === todayWd ? " today" : ""}`, "data-show": v.show },
          el("span", { class: "wk-wd" }, wdName(v.wd)),
          el("span", { class: "wk-show" }, short(v.show)),
          el("span", { class: "wk-time" }, time || "\u00a0"),
          el("span", { class: "wk-marks" }, v.pre ? el("i", { class: "wk-pre", title: t("howto_pre") }, t("wk_pre")) : null,
            v.live ? el("i", { class: "wk-live", title: t("howto_live") }, "LIVE") : null),
          live(v.show) ? el("span", { class: "wk-on", title: t("cheer_open", { n: 1 }) }) : null);
        b.addEventListener("click", () => showDetail(v));
        return b;
      }));
      $("howto").append(el("div", { class: "wk" }, el("h3", { class: "wk-title" }, t("howto_voting")), grid, detail));
      showDetail(pick);
    }
    // 나머지 가이드: 아이콘 타일 → 누른 것만 펼치기
    const ICON = [[/해외|global/i, "🌏"], [/음원|스밍/, "🎧"], [/유튜브|조회수/, "▶️"], [/라디오 신청/, "📻"], [/프로그램/, "🎙"], [/공통/, "✅"]];
    const groups = howto.streaming || [];
    if (groups.length) {
      const panel = el("div", { class: "gd-panel" });
      const tiles = el("div", { class: "gd-tiles" });
      const open = (g, btn) => {
        const was = btn.classList.contains("on");
        tiles.querySelectorAll(".gd-tile").forEach((x) => x.classList.remove("on"));
        if (was) { panel.replaceChildren(); return; }
        btn.classList.add("on");
        panel.replaceChildren(el("h3", { class: "gd-h" }, tc(g.title)), el("ol", { class: "howto-steps" }, ...g.steps.map((x) => el("li", {}, tc(x)))));
      };
      for (const g of groups) {
        const icon = (ICON.find(([rx]) => rx.test(g.title)) || [0, "📖"])[1];
        const label = tc(g.title).replace(/\s*\(.*?\)\s*/g, " ").trim();
        const b = el("button", { type: "button", class: "gd-tile", "data-title": g.title },
          el("span", { class: "gd-icon", "aria-hidden": "true" }, icon), el("span", {}, label));
        b.addEventListener("click", () => open(g, b));
        tiles.append(b);
      }
      $("howto").append(el("div", { class: "gd" }, tiles, panel));
      const first = groups.findIndex((g) => g.global && LANG !== "ko");
      if (first >= 0) tiles.children[first].click();
    }
    if (howto.checked) $("howtoChecked").textContent = t("howto_checked", { d: howto.checked.replaceAll("-", ".") });
  } else {
    $("howtoSec").remove();
  }

  if ((data.charts || []).length) {
    for (const c of data.charts) {
      const last = c.ranks[c.ranks.length - 1];
      const prev = c.ranks[c.ranks.length - 2];
      const move = last && prev ? prev[1] - last[1] : 0;
      const box = el("div", { class: "chart-row" },
        el("div", { class: "chart-meta" },
          el("b", {}, c.song), el("span", { class: "muted" }, ` · ${[c.service, c.type].filter(Boolean).join(" ")}`),
          last ? el("span", { class: "rank" }, t("rank", { n: last[1] })) : null,
          move ? el("span", { class: move > 0 ? "up" : "down" }, move > 0 ? ` ▲${move}` : ` ▼${-move}`) : null),
        c.ranks.length > 1 ? el("div", { class: "chart-box small-chart" }, el("canvas", {})) : null);
      $("charts").append(box);
    }
  } else {
    $("charts").append(empty(t("no_charts")));
  }

  // 정렬: 다가오는(진행 중 포함) 일정 날짜·시간 빠른 순 → 지난 일정 최근 순 → 날짜 없는 공지
  const _nk = (x) => (x.date || "") + " " + (x.time || "");
  const _past = (x) => (x.end_date || x.date) < todayKst;
  const notices = [...(data.notices || [])].sort((a, b) => {
    const ga = !a.date ? 2 : _past(a) ? 1 : 0, gb = !b.date ? 2 : _past(b) ? 1 : 0;
    if (ga !== gb) return ga - gb;
    return ga === 1 ? _nk(b).localeCompare(_nk(a)) : _nk(a).localeCompare(_nk(b));
  });
  // 지금 언어 지역의 판매처(langs)를 먼저 — 예: 일본어 화면이면 일본 판매처가 위로
  const mine = (x) => ((x.langs || []).includes(LANG) ? 0 : (x.langs || []).length ? 2 : 1);
  // 지역 판매처(langs 지정)는 그 언어 화면에서만
  const shops = [...(data.info?.shops || [])].filter((x) => mine(x) < 2).sort((a, b) => mine(a) - mine(b));
  // 한눈에 탭: 음반 구매처 한 번에
  if (shops.length) {
    $("shopGrid").replaceChildren(...shops.map((x) => {
      const a = ext(x.url, tc(x.label));
      a.classList.add("shop");
      if (x.note) a.append(el("span", { class: "muted small" }, tc(x.note)));
      return a;
    }));
    $("shopHome").hidden = false;
    // 오프라인 매장: 지도 + 매장별 입고 글 전부 + 어디서나 살 수 있는 체인 매장
    const offs = [...(data.info?.offline_stores || [])].filter((x) => mine(x) < 2).sort((a, b) => mine(a) - mine(b) || (b.date || "").localeCompare(a.date || ""));
    const chains = (data.info?.chain_stores || []).filter((x) => mine(x) < 2).sort((a, b) => mine(a) - mine(b));
    const mapSearch = (q) => (LANG === "ko" ? `https://map.naver.com/p/search/${encodeURIComponent(q)}` : `https://www.google.com/maps/search/${encodeURIComponent(q)}`);
    if (offs.length) {
      const credit = data.info?.offline_stores_credit;
      $("offlineNote").textContent = [t("off_desc"), credit ? t("off_credit", { who: credit }) : ""].filter(Boolean).join(" · ");
      const region = (x) => tc(String(x.area || "").split(" ")[0]);
      const regions = [...new Set(offs.map(region).filter(Boolean))];
      let rg = "", picked = null, map = null;
      const markers = new Map();
      const pick = (x, fromMap) => {
        picked = x;
        $("offlineList").querySelectorAll(".off-card").forEach((c) => c.classList.toggle("on", c.dataset.name === x.name));
        markers.forEach((m, name) => m.getElement()?.classList.toggle("on", name === x.name));
        if (map && x.lat && !fromMap) map.flyTo([x.lat, x.lng], Math.max(map.getZoom(), 14), { duration: 0.6 });
        if (fromMap) $("offlineList").querySelector(`.off-card[data-name="${CSS.escape(x.name)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      };
      const card = (x) => {
        const inDate = x.date ? t("off_in", { d: x.date.slice(5).replace("-", ".") }) : "";
        const posts = (x.posts || []).filter((p) => p.url);
        const c = el("div", { class: "off-card", "data-name": x.name, tabindex: "0" },
          el("div", { class: "off-h" }, el("b", {}, tc(x.name)), inDate ? el("span", { class: "chip" }, inDate) : null),
          el("div", { class: "muted small" }, x.addr || tc(x.area), x.approx ? el("span", { class: "off-approx" }, ` · ${t("off_approx")}`) : null),
          x.versions ? el("div", {}, el("span", { class: "chip" }, tc(x.versions))) : null,
          posts.length ? el("div", { class: "off-posts" }, ...posts.map((p) => el("a", { href: p.url, target: "_blank", rel: "noopener" },
            el("span", { class: "muted" }, p.date ? p.date.slice(5).replace("-", ".") : ""), el("span", {}, `${p.text || t("off_post")} ↗`)))) : null,
          el("div", { class: "off-links" },
            ext(mapSearch(x.name), t("off_dir"), ""),
            x.handle ? ext(`https://x.com/${x.handle}`, t("off_acct"), "") : null,
            x.site ? ext(x.site, t("off_site"), "") : null));
        c.addEventListener("click", (e) => { if (!e.target.closest("a")) pick(x); });
        return c;
      };
      const drawOff = () => {
        const list = offs.filter((x) => !rg || region(x) === rg);
        $("offRegions").replaceChildren(...(regions.length > 1 ? ["", ...regions] : []).map((r) => {
          const n = r ? offs.filter((x) => region(x) === r).length : offs.length;
          const b = el("button", { type: "button", class: r === rg ? "on" : "", "aria-pressed": String(r === rg) }, `${r || t("ev_all")} ${n}`);
          b.addEventListener("click", () => { rg = r; drawOff(); });
          return b;
        }));
        $("offlineList").replaceChildren(...list.map(card));
        if (MOBILE) fold($("offlineList"), 3);
        if (map) {
          const pts = list.filter((x) => x.lat).map((x) => [x.lat, x.lng]);
          markers.forEach((m, name) => m.setOpacity(list.some((x) => x.name === name) ? 1 : 0.25));
          if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 14 });
        }
        if (picked) pick(picked, true);
      };
      drawOff();
      // 지도는 화면에 보일 때 불러오기 (Leaflet + 오픈스트리트맵, 키 없음)
      const withPins = offs.filter((x) => x.lat);
      if (withPins.length && "IntersectionObserver" in window) {
        const io = new IntersectionObserver((es) => {
          if (!es.some((e) => e.isIntersecting)) return;
          io.disconnect();
          const css = el("link", { rel: "stylesheet", href: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css" });
          const js = el("script", { src: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js" });
          js.onload = () => {
            const L = window.L;
            $("offMap").hidden = false;
            map = L.map("offMap", { scrollWheelZoom: false, attributionControl: true });
            L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
            for (const x of withPins) {
              const m = L.marker([x.lat, x.lng], { icon: L.divIcon({ className: `off-pin${x.approx ? " approx" : ""}`, html: `<i></i><span>${tc(x.name).replace(/[<&>]/g, "")}</span>`, iconSize: [14, 14] }), title: tc(x.name) }).addTo(map);
              m.on("click", () => pick(x, true));
              markers.set(x.name, m);
            }
            // 멀리서 보면 점만, 가까이(동네 수준) 오면 매장 이름까지
            const lbl = () => $("offMap").classList.toggle("labels", map.getZoom() >= 13);
            map.on("zoomend", lbl);
            drawOff();
            lbl();
          };
          js.onerror = () => $("offMap").remove();
          document.head.append(css, js);
        }, { rootMargin: "200px" });
        io.observe($("offlineStores"));
      }
      $("offlineStores").hidden = false;
    }
    if (chains.length) {
      $("chainGrid").replaceChildren(...chains.map((x) => el("a", { class: "chain", href: mapSearch(x.q), target: "_blank", rel: "noopener" },
        el("b", {}, tc(x.name)), x.note ? el("span", { class: "muted small" }, tc(x.note)) : null, el("span", { class: "chain-go" }, t("chain_find")))));
      $("chainStores").hidden = false;
    }
  } else {
    $("shopHome").remove();
  }
  // 공지 탭 맨 위: 팬싸·영통·행사 일정을 날짜별 카드로 (지난 일정·날짜 없는 공지는 뒤로)
  if (notices.length) {
    const wd = (d) => kstDate(d).toLocaleDateString(LOCALES[LANG] || "en", { weekday: "short", timeZone: "Asia/Seoul" });
    const days = new Map();
    for (const x of notices) {
      const k = x.date || "";
      if (!days.has(k)) days.set(k, []);
      days.get(k).push(x);
    }
    // 응모 기간: 응모 예정 / 응모 중(~마감) / 오늘 마감 / 응모 끝(당첨 발표) + 진행 막대
    const md = (v) => `${v.slice(5, 10).replace("-", ".")} ${v.slice(11, 16)}`.trim();
    const applyLine = (x) => {
      if (!x.apply_end && !x.announce) return null;
      const now = Date.now(), end = x.apply_end ? kstDate(x.apply_end) : null, st = x.apply_start ? kstDate(x.apply_start) : null;
      let cls, label, text;
      if (end && st && now < st) [cls, label, text] = ["soon", t("fs_ap_soon"), t("fs_ap_from", { t: md(x.apply_start) })];
      else if (end && now < end) [cls, label, text] = [x.apply_end.slice(0, 10) === todayKst ? "today" : "open",
        x.apply_end.slice(0, 10) === todayKst ? t("fs_ap_today") : t("fs_ap_open"), t("fs_ap_until", { t: md(x.apply_end) })];
      else [cls, label, text] = ["closed", t("fs_ap_closed"), x.announce ? t("fs_announce", { d: x.announce.slice(5).replace("-", ".") }) : ""];
      const pct = end && st && now >= st && now < end ? Math.max(4, ((now - st) / (end - st)) * 100) : 0;
      return el("span", { class: `fs-apply ap-${cls}` }, el("span", { class: "ap-chip" }, label), el("span", {}, text),
        pct ? el("span", { class: "ap-bar" }, el("i", { style: `width:${pct.toFixed(0)}%` })) : null);
    };
    const kind = (x) => (x.short === "영통" ? ["fs-video", t("fs_video")] : x.short === "팬싸" ? ["fs-sign", t("fs_sign")] : ["", tc(x.label)]);
    const name = (x) => (x.short ? x.title.replace(/\s*(영상통화\s*)?팬사인회$/, "") : x.title);
    $("notices").replaceChildren(...[...days].map(([d, list]) => {
      const past = d && d < todayKst;
      const left = d ? Math.round((kstDate(d) - kstDate(todayKst)) / 86400000) : null;
      return el("div", { class: `fs-day${past ? " past" : ""}${d === todayKst ? " today" : ""}` },
        el("div", { class: "fs-date" }, d ? `${d.slice(5).replace("-", ".")} (${wd(d)})` : t("fs_nodate"),
          left != null && left >= 0 ? el("span", { class: "fs-dday" }, left ? `D-${left}` : "D-DAY") : null),
        ...list.sort((a, b) => (a.time || "99").localeCompare(b.time || "99")).map((x) => {
          const [cls, label] = kind(x);
          return el("a", { class: "fs-row", href: x.post || x.url || "#", target: "_blank", rel: "noopener" },
            el("span", { class: "fs-time" }, x.time || "—"),
            el("span", { class: `chip ${cls}` }, label),
            el("span", { class: "fs-name" }, name(x)),
            el("span", { class: "fs-go", "aria-hidden": "true" }, "↗"),
            applyLine(x));
        }));
    }));
  } else {
    $("noticesSec").remove();
  }

  // ---------- 공식 인스타 피드 ----------
  const igPost = (x, withMembers = true) => {
    const iso = x.at ? kstDate(x.at).toISOString() : null;
    return el("a", { class: "ig-post", href: x.url, target: "_blank", rel: "noopener" },
      el("div", { class: "ig-meta" }, el("span", { class: `src src-${x.account === "x" ? "x" : "ig"}` }, x.account === "x" ? "X" : "IG"),
        ageHours(iso) <= NEW_HOURS ? el("span", { class: "chip chip-on" }, "NEW") : null,
        el("span", { class: "muted" }, iso ? when(iso) : ""),
        x.likes != null ? el("span", { class: "muted" }, `♥ ${fmt(x.likes)}`) : null,
        x.comments != null ? el("span", { class: "muted" }, `💬 ${fmt(x.comments)}`) : null),
      el("div", { class: "ig-text" }, (x.text || "") + (x.more ? "…" : "")),
      withMembers && (x.members || []).length ? el("div", { class: "ig-members" }, ...x.members.map((n) => el("span", { class: "chip" }, n))) : null);
  };
  const feed = data.ig_feed || [];
  if (feed.length) {
    // 인스타 | X 두 칸 (각 칸에선 출처 배지 생략)
    const cols = [["igFeed", "igCol", feed.filter((x) => x.account !== "x")], ["xFeed", "xCol", feed.filter((x) => x.account === "x")]];
    const draw = (n) => cols.forEach(([id, , list]) => $(id).replaceChildren(...list.slice(0, n).map((x) => igPost(x))));
    cols.forEach(([, col, list]) => { if (!list.length) $(col).remove(); });
    draw(5);
    if (cols.some(([, , list]) => list.length > 5)) {
      $("igMore").hidden = false;
      $("igMore").onclick = () => { draw(99); $("igMore").remove(); };
    }
  } else {
    $("igFeedSec").remove();
  }

  // ---------- 공지 탭: 공식 공지 글 (사녹 집합 장소·공지·예약 안내) ----------
  const nposts = data.notice_posts || [];
  if (nposts.length) {
    let kind = "";
    const kinds = ["prerec", "place", "notice", "release", "schedule"].filter((k) => nposts.some((x) => x.kind === k));
    const fresh = nposts.filter((x) => ageHours(kstDate(x.at).toISOString()) <= 24).length;
    if (fresh) $("noticeTab").append(el("span", { class: "tab-dot", "aria-label": t("notice_new", { n: fresh }) }, String(fresh)));
    let draw = () => {
      $("noticeKinds").replaceChildren(...["", ...kinds].map((k) => {
        const b = el("button", { type: "button", class: k === kind ? "on" : "", "aria-pressed": String(k === kind) },
          k ? t(`notice_${k}`) : t("ev_all"));
        b.addEventListener("click", () => { kind = k; draw(); });
        return b;
      }));
      // 카드: 종류 배지 + 제목 한 줄 + 핵심 정보 칩(인원 체크 시간·신청 시간·링크) + 작은 썸네일 — 누르면 원문
      const KIND_ICO = { place: "📍", prerec: "🔔", notice: "📢", release: "💿", schedule: "🗓" };
      const fact = (f) => (f.type === "slot" ? t("np_slot", { r: f.range, t: f.time }) : f.type === "check" ? t("np_check", { t: f.time })
        : f.type === "apply" ? t("np_apply", { d: f.date, a: f.from, b: f.to }) : f.type === "link" ? `🔗 ${f.label}` : "");
      const shown = nposts.filter((x) => !kind || x.kind === kind);
      $("noticePosts").replaceChildren(...shown.slice(0, npMax).map((x) => {
        const iso = kstDate(x.at).toISOString();
        const src = (x.images || [])[0];
        let th = null;
        if (src) {
          th = el("img", { class: "np-th", src, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
          th.addEventListener("error", () => th.remove());
        }
        const facts = (x.facts || []).map(fact).filter(Boolean);
        return el("a", { class: "np", href: x.url, target: "_blank", rel: "noopener" },
          el("div", { class: "np-top" }, el("span", { class: `np-kind k-${x.kind}` }, `${KIND_ICO[x.kind] || "📢"} ${t(`notice_${x.kind}`)}`),
            ageHours(iso) <= NEW_HOURS ? el("span", { class: "chip chip-on" }, "NEW") : null,
            el("span", { class: "muted" }, `${x.account === "x" ? "X" : "IG"} · ${when(iso)}`)),
          el("div", { class: "np-body" },
            el("div", { class: "np-main" }, el("div", { class: "np-title" }, x.title || x.text.split("\n")[0]),
              x.desc ? el("div", { class: "np-desc" }, x.desc) : null,
              facts.length ? el("div", { class: "np-facts" }, ...facts.map((f) => el("span", {}, f))) : null),
            th));
      }));
    };
    let npMax = MOBILE ? 6 : 12;
    const npMore = el("button", { type: "button", class: "more np-more" }, t("more"));
    npMore.addEventListener("click", () => { npMax = 999; draw(); });
    $("noticePosts").after(npMore);
    const draw0 = draw;
    draw = () => { draw0(); npMore.hidden = nposts.filter((x) => !kind || x.kind === kind).length <= npMax; };
    draw();
  } else {
    $("noticePostsSec").append(empty(t("notice_none")));
  }

  // ---------- 공지 탭: 매체·콘텐츠 계정의 A2O SOUL 글 ----------
  const mposts = data.media_posts || [];
  if (mposts.length) {
    let acct = "";
    const accts = [...new Map(mposts.map((x) => [x.handle, x.name])).entries()];
    const draw = () => {
      $("mediaAccts").replaceChildren(...(accts.length > 1 ? [["", t("ev_all")], ...accts] : []).map(([h, name]) => {
        const b = el("button", { type: "button", class: h === acct ? "on" : "", "aria-pressed": String(h === acct) }, name);
        b.addEventListener("click", () => { acct = h; draw(); });
        return b;
      }));
      $("mediaPosts").replaceChildren(...mposts.filter((x) => !acct || x.handle === acct).map((x) => {
        const iso = kstDate(x.at).toISOString();
        const src = (x.images || [])[0];
        let thumb = null;
        if (src) {
          const img = el("img", { src, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
          img.addEventListener("error", () => thumb.remove());
          thumb = el("div", { class: "media-thumb" }, img, x.video ? el("span", { class: "media-play", "aria-label": t("media_video") }, "▶") : null);
        }
        return el("a", { class: "media-card", href: x.url, target: "_blank", rel: "noopener" },
          thumb,
          el("div", { class: "media-body" },
            el("div", { class: "ig-meta" }, el("b", {}, x.name),
              ageHours(iso) <= NEW_HOURS ? el("span", { class: "chip chip-on" }, "NEW") : null,
              el("span", { class: "muted" }, when(iso))),
            el("div", { class: "media-text" }, x.text)));
      }));
    };
    draw();
  } else {
    $("mediaPostsSec").append(empty(t("media_none")));
  }

  // ---------- 세계관·앨범 (입덕 탭) ----------
  const info = data.info || {};
  if ((info.lore || []).length) for (const p of info.lore) $("lore").append(el("p", {}, tc(p)));
  else $("loreSec").remove();
  if ((info.albums || []).length) {
    for (const a of info.albums) {
      $("albums").append(el("div", { class: "album" },
        el("div", {}, el("b", {}, a.title), a.type ? el("span", { class: "muted" }, ` · ${tc(a.type)}`) : null),
        a.date ? el("div", { class: "muted small" }, [a.date.replaceAll("-", "."), a.time].filter(Boolean).join(" ") + " KST") : null,
        a.tracks.length ? el("ol", { class: "tracks" }, ...a.tracks.map((x) => el("li", {}, x,
          (a.focus || []).some((f) => f.toLowerCase() === x.toLowerCase()) ? el("span", { class: "chip chip-on focus" }, t("focus_track")) : null))) : null,
        a.note ? el("div", { class: "muted small" }, tc(a.note)) : null,
        a.versions.length ? el("div", { class: "small" }, el("span", { class: "chip" }, t("album_versions")),
          el("ul", { class: "versions" }, ...a.versions.map((x) => el("li", {}, tc(x))))) : null,
        Object.keys(a.links).length ? el("div", { class: "links small" }, ...Object.entries(a.links).map(([k, u]) => ext(u, k))) : null));
    }
  } else {
    $("albumsSec").remove();
  }

  const supports = data.supports || [];
  if (supports.length) {
    for (const x of supports) {
      const running = x.start <= todayKst;
      $("supports").append(el("div", { class: "support" },
        el("div", {}, el("span", { class: `chip ${running ? "chip-on" : ""}` }, x.kind || "-"),
          el("b", {}, [x.member, x.title].filter(Boolean).join(" "))),
        el("div", { class: "muted" }, `${x.start.slice(5).replace("-", ".")} ~ ${x.end.slice(5).replace("-", ".")}`,
          x.place ? ` · ${x.place}` : "", x.host ? ` · ${t("host", { v: x.host })}` : ""),
        x.url ? ext(x.url, "↗") : null));
    }
  } else {
    $("supports").append(empty(t("no_supports")));
  }

  const icsUrl = new URL("data/calendar.ics", location.href).href;
  const webcal = icsUrl.replace(/^https?:/, "webcal:");
  $("calLinks").append(
    el("a", { href: webcal }, t("cal_apple")),
    ext(`https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`, t("cal_google")),
  );
  const copyBtn = el("button", { type: "button", class: "linkbtn" }, t("cal_copy"));
  copyBtn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(icsUrl); copyBtn.textContent = t("copied"); } catch (_) { prompt("URL", icsUrl); }
  });
  $("calLinks").append(copyBtn);
  $("votesSec").append(el("p", { class: "small wk-cal" }, `📅 ${t("wk_cal")} `,
    el("a", { href: webcal }, t("cal_apple")), " · ", ext(`https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`, t("cal_google"))));

  // ---------- 응원 탭 맨 위 메뉴: 할 일을 타일로 한눈에, 누르면 해당 칸으로 ----------
  {
    const cnt = (id, sel) => ($(id) ? $(id).querySelectorAll(sel).length : 0);
    const rg = (data.howto?.streaming || []).find((g) => /라디오/.test(g.title));
    const radio = rg && document.querySelector(`#howto .gd-tile[data-title="${CSS.escape(rg.title)}"]`);
    const tiles = [
      ["🎙", "prerec", "prerecSec", cnt("prerecs", ".vote"), true],
      ["🗳", "votes", "votesSec", cnt("votes", ".vt"), true],
      ["🎧", "streaming", "streamSec"],
      ["📣", "fanchants", "fanchantSec"],
      ["📻", "cheer_radio", radio],
      ["📖", "howto", "howtoSec"],
      ["📊", "charts", "chartsSec"],
      ["🎂", "supports", "supportsSec", cnt("supports", ".support"), true],
      ["📅", "calendar", "calendarSec"],
    ];
    const items = tiles.map(([icon, key, target, n, counted]) => {
      const node = typeof target === "string" ? $(target) : target;
      if (!node) return null;
      const b = el("button", { type: "button", class: `cm-tile${counted && n ? " on" : ""}` },
        el("span", { class: "cm-icon", "aria-hidden": "true" }, icon),
        el("span", { class: "cm-label" }, t(key)),
        counted ? el("span", { class: "cm-sub" }, n ? t("cheer_open", { n }) : t("cheer_none")) : null);
      b.addEventListener("click", () => {
        if (node.tagName === "DETAILS") node.open = true;
        if (node.classList?.contains("gd-tile") && !node.classList.contains("on")) node.click();
        node.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      return b;
    }).filter(Boolean);
    if (items.length) $("cheerMenu").append(...items);
    else $("cheerMenu").remove();
  }

  // ---------- MV ----------
  const goal = (f) => (f
    ? el("div", { class: "m goal", title: t("goal_tip") }, t("goal", { target: kr(f.target), days: f.days, rate: kr(f.rate) }))
    : el("div", { class: "m goal" }, t("goal_pending")));
  const mvs = [...data.mvs].sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  if (mvs.length) {
    for (const v of mvs) $("mvList").append(videoCard(v, null, goal(v.forecast)));
  } else {
    $("mvList").replaceWith(empty(t("empty_mv")));
  }

  // ---------- 멤버 ----------
  const dlg = $("memberDialog");
  $("dlgClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => { if (route()[0] === "member") history.replaceState(null, "", "#members"); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }); // 바깥 클릭으로 닫기
  // 인스타그램 공식 임베드 (instagram.com/p|reel/코드 형식만 허용)
  function igEmbeds(urls) {
    return (urls || []).map((u) => /instagram\.com\/(p|reel)\/([\w-]+)/.exec(u)).filter(Boolean)
      .map(([, kind, code]) => el("iframe", {
        class: "ig-embed", src: `https://www.instagram.com/${kind}/${code}/embed`, loading: "lazy",
        title: "Instagram", allowtransparency: "true", scrolling: "no", referrerpolicy: "strict-origin-when-cross-origin",
      }));
  }
  const bdayText = (m) => {
    if (!/^\d{2}-\d{2}$/.test(m.birthday || "")) return "";
    const mo = +m.birthday.slice(0, 2), d = +m.birthday.slice(3);
    return t("bday", { m: mo, d, mon: (t("months") || [])[mo - 1] || mo });
  };
  const facts = (m, withBday) => [tc(m.position), m.birth_year ? t("born", { y: m.birth_year }) : "",
    withBday ? bdayText(m) : "", nat(m.nationality)].filter(Boolean).join(" · ");

  function profile(m) {
    const list = (label, items) => (items.length
      ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, label), el("ul", {}, ...items.map((x) => el("li", {}, x))))
      : null);
    const embeds = igEmbeds(m.instagram_posts);
    const tip = (data.guide?.tips || {})[m.name];
    return el("section", { class: "dlg-sec profile" },
      embeds.length ? el("div", { class: "ig-row" }, ...embeds) : null,
      el("div", { class: "pf-facts" }, facts(m, true)),
      m.nicknames.length ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("nickname")), el("div", {}, m.nicknames.map(tc).join(", "))) : null,
      tip ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, "Tip"), el("div", {}, tip)) : null,
      list(t("career"), m.career.map(tc)),
      list(t("notes"), m.notes.map(tc)),
      m.signature ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("signature")),
        el("img", { class: "pf-sign", src: m.signature, alt: "", loading: "lazy" })) : null,
      (m.profile_history || []).length ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("history")),
        el("div", { class: "pf-history", tabindex: "0" }, ...m.profile_history.map((h) => el("figure", {},
          h.photo ? el("img", { src: h.photo, alt: h.label, loading: "lazy" }) : igEmbeds([h.instagram])[0],
          h.label ? el("figcaption", {}, h.label) : null)))) : null);
  }

  const avatar = (m, cls = "avatar") => el("div", { class: cls, "aria-hidden": "true" },
    m.photo ? el("img", { src: m.photo, alt: "", loading: "lazy" }) : (m.ko ? m.ko[0] : m.name[0]));

  // ---------- 포토카드 크게 보기: 누르면 크게, 좌우 버튼·스와이프·방향키로 넘기기 ----------
  function openPcViewer(list, idx) {
    const dlg = $("pcView");
    let i = idx;
    const show = () => {
      const x = list[i];
      $("pcViewImg").src = x.src;
      $("pcViewImg").alt = `${x.member} ${tc(x.version)} ${x.label}`;
      $("pcViewCap").textContent = `${x.member} · ${tc(x.version)}${x.label ? ` · ${x.label}` : ""}  (${i + 1}/${list.length})`;
    };
    const go = (d) => { i = (i + d + list.length) % list.length; show(); };
    $("pcPrev").onclick = () => go(-1);
    $("pcNext").onclick = () => go(1);
    $("pcClose").onclick = () => dlg.close();
    dlg.onkeydown = (e) => { if (e.key === "ArrowLeft") go(-1); if (e.key === "ArrowRight") go(1); };
    let x0 = null;
    dlg.ontouchstart = (e) => { x0 = e.touches[0].clientX; };
    dlg.ontouchend = (e) => { if (x0 == null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1); x0 = null; };
    dlg.onclick = (e) => { if (e.target === dlg) dlg.close(); };
    show();
    const top = document.querySelector("dialog[open]:not(#pcView)");
    if (top && !dlg.open) top.after(dlg);  // 멤버 창 위에 뜨도록
    dlg.showModal();
  }
  const pcBtn = (x, list, i, caption) => {
    const b = el("button", { type: "button", class: "pc", "aria-label": `${x.member} ${tc(x.version)} ${x.label}` },
      el("img", { src: x.src, alt: "", loading: "lazy", decoding: "async" }), caption);
    b.addEventListener("click", () => openPcViewer(list, i));
    return b;
  };

  function openMember(m, focus) {
    const star = el("button", { class: "bias-btn", type: "button" });
    const paintStar = () => {
      const on = bias === m.name;
      star.classList.toggle("on", on);
      star.setAttribute("aria-label", on ? t("bias_on") : t("bias_set"));
      star.replaceChildren(on ? "★" : "☆", el("span", { class: "bias-l" }, ` ${on ? t("bias_on") : t("bias_set")}`));
    };
    paintStar();
    star.addEventListener("click", () => { setBias(bias === m.name ? "" : m.name); paintStar(); });
    $("dlgTitle").replaceChildren(avatar(m, "avatar dlg-avatar"), el("span", {}, m.name),
      m.ko ? el("span", { class: "dlg-ko" }, m.ko) : null, star,
      shareBtn(() => share(`member/${m.name}`, `A2O SOUL ${m.name}`)));
    const sections = [profile(m)];
    for (const [key, label, list] of [["fancams", "fancams_n", m.fancams], ["predebut", "predebut_n", m.predebut]]) {
      if (!list.length) continue;
      sections.push(el("section", { class: "dlg-sec", id: `dlg-${key}` },
        el("h3", {}, t(label, { n: list.length })),
        el("div", { class: "videos" }, ...list.map((v) => videoCard(v, null)))));
    }
    // 더 찾아보기: 데뷔 전 이름(별칭)까지 넣어 유튜브·빌리빌리 검색 (연습실·커버 영상 등 사이트에 없는 것)
    {
      const names = [m.name, (m.aliases || [])[0]].filter(Boolean);
      const q = encodeURIComponent(`A2O ${names.join(" ")}`);
      sections.push(el("section", { class: "dlg-sec", id: "dlg-more" },
        el("h3", {}, t("more_search")),
        el("div", { class: "links small" },
          ext(`https://www.youtube.com/results?search_query=${q}`, "YouTube ↗"),
          ext(`https://search.bilibili.com/all?keyword=${q}`, "bilibili ↗"))));
    }
    const myPc = (data.photocards || []).filter((x) => x.member === m.name);
    if (myPc.length) {
      const cr = (data.info || {}).photocard_credit || {};
      sections.push(el("section", { class: "dlg-sec", id: "dlg-pc" },
        el("h3", {}, `${t("photocards")} ${myPc.length}`),
        el("div", { class: "pc-grid" }, ...myPc.map((x, i) => pcBtn(x, myPc, i,
          el("span", { class: "pc-cap muted" }, `${tc(x.version)} · ${x.label}`)))),
        cr.url ? el("p", { class: "pf-src" }, t("pc_credit"), " ", ext(cr.url, cr.label || cr.url)) : null));
    }
    if ((m.ig_mentions || []).length) {
      sections.push(el("section", { class: "dlg-sec", id: "dlg-ig" },
        el("h3", {}, t("ig_mentions", { n: m.ig_mentions.length })),
        el("div", { class: "ig-feed" }, ...m.ig_mentions.map((x) => igPost(x, false)))));
    }
    // 출처는 맨 아래 작게
    sections.push(el("div", { class: "pf-src" }, t("source"),
      ext(`https://namu.wiki/w/${encodeURIComponent(`${m.ko}(A2O SOUL)`)}`, "namu.wiki")));
    $("dlgBody").replaceChildren(...sections);
    if (route()[0] !== "member" || route()[1] !== m.name) history.replaceState(null, "", `#member/${encodeURIComponent(m.name)}`);
    dlg.showModal();
    dlg.scrollTop = 0;
    if (focus) $(`dlg-${focus}`)?.scrollIntoView();
  }

  for (const l of data.group_links || []) $("groupLinks").append(ext(l.url, tc(l.label), " ↗"));
  if (!(data.group_links || []).length) $("groupLinks").closest("section").remove();
  const gp = igEmbeds(data.group_posts);
  if (gp.length) $("groupPosts").append(...gp); else $("groupPostsSec").remove();
  $("membersHead").textContent = t("members_n", { n: data.members.length });
  // 활동별 사진 보기: 역대 프로필 라벨(곡명)마다 15명 카드 사진을 한 번에 바꾸기
  const eras = [...new Set(data.members.flatMap((m) => (m.profile_history || []).filter((h) => h.photo && h.label).map((h) => h.label)))];
  if (eras.length >= 2) {
    const row = el("div", { class: "filter-row era-row" });
    let cur = pref.get("era", "");
    const paint = () => {
      row.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.era === cur));
      document.querySelectorAll(".pcard[data-name]").forEach((c) => {
        const m = data.members.find((x) => x.name === c.dataset.name);
        const src = (cur && (m.profile_history || []).find((h) => h.label === cur)?.photo) || m.photo;
        const img = c.querySelector(".avatar img");
        if (img && src) img.src = src;
      });
    };
    for (const e of eras) {
      const b = el("button", { type: "button", "data-era": e }, e);
      b.addEventListener("click", () => { cur = cur === e ? "" : e; pref.set("era", cur); paint(); });
      row.append(b);
    }
    $("profiles").before(row);
    queueMicrotask(paint);
  }
  for (const m of data.members) {
    const card = el("button", { class: "pcard", type: "button", "data-name": m.name },
      avatar(m),
      el("div", { class: "pinfo" },
        el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.ko)),
        el("div", { class: "s" }, facts(m, false)),
        m.nicknames.length ? el("div", { class: "s" }, t("nick_line", { v: m.nicknames.map(tc).join(", ") })) : null,
        el("div", { class: "s more-link" }, t("profile_view"))));
    card.addEventListener("click", () => openMember(m));
    $("profiles").append(card);
  }
  if (MOBILE) fold($("profiles"), 6);

  // ---------- 직캠 / 입덕 가이드: 멤버별 최신 직캠 카드 ----------
  function fancamCard(m) {
    const v = m.fancams[0] || m.predebut[0]; // 최신 직캠, 없으면 데뷔 전 영상
    const links = [];
    if (m.fancams.length) links.push(["fancams", t("fancam_short", { n: m.fancams.length })]);
    if (m.predebut.length) links.push(["predebut", t("predebut_short", { n: m.predebut.length })]);
    const tip = (data.guide?.tips || {})[m.name];
    const card = el("button", { class: "member", type: "button" },
      v ? el("img", { src: thumbUrl(v.id), alt: "", loading: "lazy" }) : el("div", { class: "nothumb" }, t("fancam_pending")),
      el("div", { class: "n" }, m.name, el("span", { class: "c" }, tc(m.position) || nat(m.nationality))),
      tip ? el("div", { class: "s tip" }, tip) : (v ? el("div", { class: "t" }, v.title) : null),
      v ? el("div", { class: "s" }, `${ymd(v.published_at)} · ${t("views", { v: kr(v.views ?? 0) })}`) : null,
      links.length ? el("div", { class: "s more-link" }, links.map((l) => l[1]).join(" · ") + t("view")) : null);
    card.addEventListener("click", () => openMember(m, links[0]?.[0]));
    return card;
  }
  for (const m of data.members) $("members").append(fancamCard(m));
  for (const m of data.members) $("guideMembers").append(fancamCard(m));
  if (MOBILE) { fold($("members"), 6); fold($("guideMembers"), 6); }

  // 처음 오셨나요? (첫 번째 카드만 펼쳐 둠)
  const beg = data.guide?.beginner || [];
  if (beg.length) {
    beg.forEach((b, i) => $("beginner").append(el("details", { class: "howto", ...(i === 0 ? { open: "" } : {}) },
      el("summary", {}, tc(b.title)), el("ol", { class: "howto-steps" }, ...b.items.map((x) => el("li", {}, tc(x)))))));
  } else {
    $("beginnerSec").remove();
  }
  const course = data.guide?.course || [];
  if (course.length) {
    course.forEach((c, i) => $("course").append(el("li", {},
      el("span", { class: "step" }, String(i + 1)),
      el("div", { class: "course-card" }, c.note ? el("div", { class: "course-note" }, tc(c.note)) : null,
        videoCard(c, c.member || catLabel(c.category))))));
    if (MOBILE) fold($("course"), 3);
  } else {
    $("course").closest("section").remove();
  }

  // ---------- 영상 아카이브 ----------
  const CATS = [
    ["all", () => true],
    ["mv", (v) => v.category === "mv"],
    ["fancam", (v) => v.category === "fancam"],
    ["stage", (v) => v.show && v.category !== "fancam"],
    ["content", (v) => v.category === "content" && !v.predebut && !v.show],
    ["predebut", (v) => v.predebut],
  ];
  const FORMATS = [
    ["all", () => true],
    ["long", (v) => !v.short],
    ["short", (v) => v.short],
  ];
  const PAGE = MOBILE ? 12 : 24;
  const cur = { cat: "all", fmt: "all", q: "", series: "", show: "", era: "", unseen: false };
  let shown = 0;
  const chipOf = (v) => (v.predebut ? catLabel("predebut") : v.member || tc(v.series) || catLabel(v.category));
  const pick = (defs, key) => defs.find((d) => d[0] === key)[1];
  const norm = (s) => (s || "").toLowerCase().normalize("NFKC");
  const base = (v) => (!cur.q || norm(v.title).includes(norm(cur.q)) || norm(v.member).includes(norm(cur.q)))
    && (!cur.series || v.series === cur.series) && (!cur.show || v.show === cur.show) && (!cur.era || v.era === cur.era) && (!cur.unseen || !seen.has(v.id));
  const current = () => data.videos.filter((v) => base(v) && pick(CATS, cur.cat)(v) && pick(FORMATS, cur.fmt)(v));
  function renderVideos(reset) {
    const list = current();
    if (reset) { $("allVideos").replaceChildren(); shown = 0; }
    $("allVideos").append(...list.slice(shown, shown + PAGE).map((v) => videoCard(v, chipOf(v))));
    shown = Math.min(shown + PAGE, list.length);
    $("more").hidden = shown >= list.length;
    if (!list.length) $("allVideos").append(empty(t("no_match")));
  }
  function filterRow(defs, slot, prefix, countFn) {
    const row = el("div", { class: "filter-row" });
    const buttons = defs.map(([key]) => {
      const b = el("button", { type: "button", "data-key": key });
      b.addEventListener("click", () => { cur[slot] = key; refresh(); });
      row.append(b);
      return b;
    });
    return { row, update: () => buttons.forEach((b) => {
      const key = b.dataset.key;
      b.classList.toggle("on", cur[slot] === key);
      b.textContent = `${t(`${prefix}.${key}`)} ${countFn(key)}`;
    }) };
  }
  const catRow = filterRow(CATS, "cat", "cat", (k) => data.videos.filter((v) => base(v) && pick(CATS, k)(v) && pick(FORMATS, cur.fmt)(v)).length);
  const fmtRow = filterRow(FORMATS, "fmt", "fmt", (k) => data.videos.filter((v) => base(v) && pick(CATS, cur.cat)(v) && pick(FORMATS, k)(v)).length);
  const unseenBtn = el("button", { type: "button", class: "unseen-btn" });
  unseenBtn.addEventListener("click", () => { cur.unseen = !cur.unseen; refresh(); });
  fmtRow.row.append(unseenBtn);
  $("filters").append(catRow.row, fmtRow.row);
  function fillSelect(sel, allLabel, values, slot) {
    sel.setAttribute("aria-label", allLabel);
    sel.append(el("option", { value: "" }, allLabel), ...values.map((x) => el("option", { value: x }, tc(x))));
    sel.addEventListener("change", () => { cur[slot] = sel.value; refresh(); });
    if (!values.length) sel.hidden = true;
  }
  const uniq = (arr) => [...new Set(arr.filter(Boolean))];
  fillSelect($("seriesSel"), t("series_all"), uniq(data.videos.map((v) => v.series)).sort(), "series");
  fillSelect($("showSel"), t("show_all"), uniq(data.videos.map((v) => v.show)).sort(), "show");
  // 활동: 최근 활동 먼저 (영상 목록에서 처음 나온 순서 = 최신순)
  fillSelect($("eraSel"), t("era_all"), uniq(data.videos.map((v) => v.era)), "era");
  $("search").placeholder = t("search");
  let timer;
  $("search").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { cur.q = e.target.value.trim(); refresh(); }, 150); });
  function refresh() {
    catRow.update(); fmtRow.update();
    unseenBtn.classList.toggle("on", cur.unseen);
    unseenBtn.textContent = `${t("unseen_only")} ${data.videos.filter((v) => !seen.has(v.id)).length}`;
    renderVideos(true);
  }
  $("more").addEventListener("click", () => renderVideos(false));
  refresh();

  // ---------- 응원법 (응원 탭) ----------
  const chants = data.fanchants || [];
  const guides = (data.info || {}).fanchant_guides || [];
  // 응원법: 곡 탭으로 한 곡씩 — 왼쪽 공식 가이드 이미지(누르면 원본), 오른쪽 멤버 콜·응원법 영상·링크
  const call = (data.info || {}).fanchant_call;
  const ytId = (u) => (/(?:youtu\.be\/|v=|shorts\/)([\w-]{11})/.exec(u || "") || [])[1];
  const used = new Set();
  const songVideo = (g) => {
    const id = ytId(g.video) || (chants.find((v) => v.song && g.song && v.song.toLowerCase() === g.song.toLowerCase()) || {}).id;
    if (id) used.add(id);
    return id;
  };
  const guideVids = guides.map(songVideo);
  let gi = 0;
  const drawChant = () => {
    const g = guides[gi];
    const img = el("img", { src: g.full ? g.full.replace("name=orig", "name=large") : g.src, alt: `${g.song} ${t("fanchants")}`, loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
    if (g.full) img.addEventListener("error", () => { if (img.src !== new URL(g.src, location.href).href) img.src = g.src; }, { once: true });
    const vid = guideVids[gi];
    let player = null;
    if (vid) {
      player = el("button", { type: "button", class: "fc-vid", "aria-label": t("chant_video") },
        el("img", { src: `https://i.ytimg.com/vi/${vid}/hqdefault.jpg`, alt: "", loading: "lazy" }), el("b", { "aria-hidden": "true" }, "▶"));
      player.addEventListener("click", () => player.replaceWith(el("div", { class: "fc-vid" }, el("iframe", {
        src: `https://www.youtube-nocookie.com/embed/${vid}?autoplay=1&playsinline=1&rel=0`, title: `${g.song} ${t("chant_video")}`,
        allow: "autoplay; encrypted-media; picture-in-picture; fullscreen", allowfullscreen: "" }))));
    }
    const callBox = call && (call.lines || []).length && (!call.song || !g.song || call.song.toLowerCase() === g.song.toLowerCase())
      ? el("div", { class: "fc-box" }, el("h4", {}, t("chant_call")), el("p", { class: "muted small" }, t("chant_call_desc")),
        el("div", { class: "fc-roll" }, ...call.lines.flat().map((x) => {
          const [ko, rom] = String(x).split("|");
          return el("span", { class: "call-name" }, el("b", { lang: "ko" }, ko), rom ? el("small", {}, rom) : null);
        })))
      : null;
    $("chantGuides").replaceChildren(...[
      guides.length > 1 ? el("div", { class: "filter-row era-row fc-tabs" }, ...guides.map((x, i) => {
        const b = el("button", { type: "button", class: i === gi ? "on" : "", "aria-pressed": String(i === gi) }, x.song);
        b.addEventListener("click", () => { gi = i; drawChant(); });
        return b;
      })) : null,
      el("div", { class: `fc-wrap${callBox || player ? "" : " solo"}` },
        el("a", { href: g.full || g.src, target: "_blank", rel: "noopener", class: "fc-img" }, img),
        el("div", { class: "fc-side" }, callBox, player,
          el("div", { class: "fc-acts" }, ext(g.full || g.src, `🔍 ${t("chant_zoom")}`), g.post ? ext(g.post, `↗ ${t("chant_post")}`) : null)))].filter(Boolean));
  };
  if (guides.length) drawChant();
  else if (call && (call.lines || []).length) {
    $("chantGuides").append(el("div", { class: "chant-call" },
      el("h3", {}, `${t("chant_call")} · ${call.song}`), el("p", { class: "muted small" }, t("chant_call_desc")),
      ...call.lines.map((ln) => el("div", { class: "call-line" }, ...ln.map((x) => {
        const [ko, rom] = String(x).split("|");
        return el("span", { class: "call-name" }, el("b", { lang: "ko" }, ko), rom ? el("small", {}, rom) : null);
      })))));
  }
  const rest = chants.filter((v) => !used.has(v.id));
  if (rest.length) $("fanchants").append(...rest.map((v) => videoCard(v, v.song || null)));
  if (!chants.length && !guides.length) $("fanchantSec").remove();

  // 같은 회차에 같은 멤버 직캠이 여러 개면 종류로 구분: 가로/세로, [MPD직캠]/[입덕직캠] 등
  const camTag = (v) => ((/^\[([^\]]+)\]/.exec(v.title || "") || [])[1] || "").replace(/\b[48]K\b/gi, "").trim();
  const camName = (v, all) => {
    const same = all.filter((x) => x.member && x.member === v.member && x.category === "fancam");
    if (same.length < 2) return v.member;
    const tags = same.map(camTag);
    const horiz = (tag) => /가로|horizontal/i.test(tag);
    let label;
    if (tags.some(horiz) && !tags.every(horiz)) label = horiz(camTag(v)) ? t("cam_h") : t("cam_v");
    else if (new Set(tags).size === same.length) label = camTag(v) || "";
    else label = `#${same.indexOf(v) + 1}`;
    return label ? `${v.member} · ${label}` : v.member;
  };

  // ---------- 음방 회차별 무대 (영상 탭) ----------
  const eps = data.episodes || [];
  // 영상 탭 위 음방별 탭 — 회차별 무대·전체 영상 둘 다 거름
  {
    const shows = [...new Set([...eps.map((e) => e.show), ...data.videos.map((v) => v.show)].filter(Boolean))];
    const order = (data.howto?.voting || []).map((v) => v.show);
    shows.sort((a, b) => ((order.indexOf(a) + 1) || 99) - ((order.indexOf(b) + 1) || 99) || a.localeCompare(b));
    let curShow = "";
    const drawTabs = () => {
      $("showTabs").replaceChildren(...[["", t("show_all")], ...shows.map((x) => [x, tc(x)])].map(([k, label]) => {
        const n = k ? eps.filter((e) => e.show === k).length : eps.length;
        const b = el("button", { type: "button", class: k === curShow ? "on" : "", "aria-pressed": String(k === curShow), "data-k": k }, n ? `${label} ${n}` : label);
        b.addEventListener("click", () => {
          curShow = k;
          drawTabs();
          epVisible();
          const sel = $("showSel");
          if (sel) { sel.value = k; sel.dispatchEvent(new Event("change")); }
        });
        return b;
      }));
    };
    if (shows.length) drawTabs(); else $("showTabs").remove();
  }
  const EP_FIRST = 5; // 처음엔 최근 회차 몇 개만 — 나머지는 '이전 회차 더 보기'
  let epAll = false;
  const epVisible = () => {
    const showSel = document.querySelector("#showTabs button.on");
    const k = showSel && showSel.dataset.k ? showSel.dataset.k : "";
    let shown = 0;
    document.querySelectorAll("#episodes > details.ep").forEach((d) => {
      const match = !k || d.dataset.show === k;
      d.hidden = !match || (!k && !epAll && shown >= EP_FIRST);
      if (match) shown += 1;
    });
    const rest = k ? 0 : Math.max(0, eps.length - EP_FIRST);
    const mb = $("epMore");
    if (mb) { mb.hidden = epAll || !rest; mb.textContent = `${t("ep_more")} (${rest}) ⌄`; }
  };
  if (eps.length) {
    const wd = t("weekdays");
    for (const ep of eps) {
      const day = wd[new Date(`${ep.date}T12:00:00Z`).getUTCDay()];
      const grid = el("div", { class: "videos" });
      const stage = ep.videos.find((v) => v.category !== "fancam") || ep.videos[0];
      const nCam = ep.videos.filter((v) => v.category === "fancam").length;
      const counts = [nCam < ep.videos.length ? t("ep_stage_n", { n: ep.videos.length - nCam }) : "", nCam ? t("ep_cam_n", { n: nCam }) : ""].filter(Boolean).join(" · ");
      const box = el("details", { class: "howto ep", id: `ep-${ep.date}-${ep.show}`, "data-show": ep.show },
        el("summary", {}, el("span", { class: "ep-sum" },
          stage ? el("img", { class: "ep-thumb", src: thumbUrl(stage.id), alt: "", loading: "lazy", decoding: "async" }) : null,
          el("span", {}, el("b", {}, `${ep.date.slice(5).replace("-", ".")} (${day}) ${tc(ep.show)}`),
            el("span", { class: "muted small ep-sub" }, `${ep.ep ? `EP.${ep.ep} · ` : ""}${counts}`)))),
        grid);
      // 펼칠 때 카드 만들기 (썸네일을 한꺼번에 불러오지 않게)
      box.addEventListener("toggle", () => {
        if (!box.open || grid.childElementCount) return;
        box.insertBefore(el("div", { class: "ep-tools" }, shareBtn(() => share(`ep/${ep.date}/${ep.show}`, `A2O SOUL ${ep.date} ${ep.show}`))), grid);
        const cams = ep.videos.filter((v) => v.category === "fancam" && v.member);
        if (cams.length >= 2) {
          const btn = el("button", { class: "more cmp-open", type: "button" }, `▶▶ ${t("cmp_open")}`);
          btn.addEventListener("click", () => openCompare(ep, cams));
          box.insertBefore(btn, grid);
        }
        grid.append(...ep.videos.map((v) => videoCard(v, v.member ? camName(v, ep.videos) : (v.category === "fancam" ? catLabel("fancam") : catLabel("stage")))));
      });
      $("episodes").append(box);
    }
    const mb = el("button", { type: "button", class: "more", id: "epMore" });
    mb.addEventListener("click", () => { epAll = true; epVisible(); });
    $("episodes").after(mb);
    epVisible();
  } else {
    $("episodesSec").remove();
  }

  // ---------- 직캠 나란히 보기 ----------
  const cmpDlg = $("compareDialog");
  $("cmpClose").addEventListener("click", () => cmpDlg.close());
  cmpDlg.addEventListener("close", () => {
    $("cmpBody").replaceChildren(); // 닫으면 재생 멈춤
    if (route()[0] === "cmp") history.replaceState(null, "", "#fancams");
  });
  function openCompare(ep, cams, pre = []) {
    $("cmpTitle").replaceChildren(`${ep.date.slice(5).replace("-", ".")} ${tc(ep.show)}`,
      shareBtn(() => share(`cmp/${ep.date}/${ep.show}/${cams[+slots[0].sel.value].member}/${cams[+slots[1].sel.value].member}`,
        `A2O SOUL ${ep.show} ${cams[+slots[0].sel.value].member} vs ${cams[+slots[1].sel.value].member}`)));
    const embed = (id) => `https://www.youtube-nocookie.com/embed/${id}?playsinline=1&rel=0&modestbranding=1&autoplay=1&mute=1`;
    const want = [0, 1].map((i) => { const k = cams.findIndex((v) => v.member === pre[i]); return k >= 0 ? k : i; });
    const slots = [0, 1].map((i) => {
      const sel = el("select", { class: "sel", "aria-label": `${t("cmp_open")} ${i + 1}` }, ...cams.map((v, j) => el("option", { value: j, ...(j === want[i] ? { selected: "" } : {}) }, camName(v, cams))));
      const frame = el("div", { class: "cmp-frame" });
      const load = () => {
        const v = cams[+sel.value];
        frame.replaceChildren(el("iframe", { src: embed(v.id), title: v.title, allow: "autoplay; encrypted-media; picture-in-picture; fullscreen",
          allowfullscreen: "", loading: "lazy" }));
        setSeen(v.id, true);
      };
      sel.addEventListener("change", load);
      return { sel, frame, load };
    });
    const go = el("button", { class: "more", type: "button" }, `▶ ${t("cmp_play")}`);
    go.addEventListener("click", () => slots.forEach((x) => x.load()));
    $("cmpBody").replaceChildren(
      el("div", { class: "cmp-pick" }, slots[0].sel, el("span", { class: "muted" }, "vs"), slots[1].sel, go),
      el("p", { class: "note small cmp-desc" }, t("cmp_desc")),
      el("div", { class: "cmp-grid" }, slots[0].frame, slots[1].frame));
    cmpDlg.showModal();
  }

  // 직캠 탭에서 회차 고르고 바로 나란히 보기
  const cmpEps = (data.episodes || []).map((ep) => ({ ep, cams: ep.videos.filter((v) => v.category === "fancam" && v.member) }))
    .filter((x) => x.cams.length >= 2);
  if (cmpEps.length) {
    const wd2 = t("weekdays");
    $("cmpEp").setAttribute("aria-label", t("cmp_pick"));
    $("cmpEp").append(el("option", { value: "" }, t("cmp_pick")), ...cmpEps.map((x, i) => el("option", { value: i },
      `${x.ep.date.slice(5).replace("-", ".")} (${wd2[new Date(`${x.ep.date}T12:00:00Z`).getUTCDay()]}) ${tc(x.ep.show)} · ${t("fancams_n", { n: x.cams.length })}`)));
    $("cmpEp").addEventListener("change", (e) => {
      if (e.target.value === "") return;
      const x = cmpEps[+e.target.value];
      openCompare(x.ep, x.cams);
      e.target.value = "";
    });
  } else {
    $("cmpSec").remove();
  }

  // ---------- 데뷔 전 아카이브 (영상 탭) ----------
  const pre = data.videos.filter((v) => v.predebut);
  if (pre.length) {
    const unitOf = (v) => (/\bLTB\b/.test(v.title) ? "LTB" : /\bHTB\b/.test(v.title) ? "HTB" : "etc");
    for (const unit of ["LTB", "HTB", "etc"]) {
      const list = pre.filter((v) => unitOf(v) === unit);
      if (!list.length) continue;
      const months = [...new Set(list.map((v) => (v.published_at || "").slice(0, 7)))].sort().reverse();
      const span = months.length ? `${months[months.length - 1].replace("-", ".")}–${months[0].replace("-", ".")}` : "";
      const body = el("div", { class: "arc-body" });
      const box = el("details", { class: "howto" },
        el("summary", {}, el("span", {}, el("b", {}, unit === "etc" ? t("arc_etc") : unit),
          el("span", { class: "muted" }, ` · ${span} · ${t("videos_n", { n: list.length })}`))), body);
      box.addEventListener("toggle", () => {
        if (!box.open || body.childElementCount) return;
        for (const mo of months) {
          const vs = list.filter((v) => (v.published_at || "").startsWith(mo));
          body.append(el("h3", { class: "arc-month" }, mo.replace("-", ".")),
            el("div", { class: "videos" }, ...vs.map((v) => videoCard(v, (v.members || []).length === 1 ? v.members[0] : null))));
        }
      });
      $("archive").append(box);
    }
  } else {
    $("archiveSec").remove();
  }

  // ---------- 생일 카드 (한눈에 맨 위, 생일 당일 KST) ----------
  const todayMD = new Date(Date.now() + 9 * 3600000).toISOString().slice(5, 10);
  const bdays = data.members.filter((m) => m.birthday === todayMD);
  if (bdays.length) {
    $("bdayCard").append(...bdays.map((m) => {
      const b = el("button", { class: "bday-card", type: "button" },
        m.photo ? el("img", { src: m.photo, alt: "" }) : null,
        el("div", {}, el("div", { class: "bday-t" }, t("bday_today", { name: m.name })),
          el("div", { class: "muted small" }, `${m.ko} · ${t("bday_sub")}`)));
      b.addEventListener("click", () => openMember(m));
      return b;
    }));
  } else {
    $("bdayCard").remove();
  }

  // ---------- 기록 (입덕 탭) ----------
  const tl = (data.timeline || []).filter((x) => !(x.kind === "anniv" && !x.n));  // '🎉 데뷔'(0주년)는 '데뷔'와 겹쳐서 뺌
  if (tl.length) {
    // 음방 첫 무대들은 한 줄로 묶기: 첫 음방 무대 · 10.15 엠카운트다운 · 10.19 SHOW K-POP …
    const shows = tl.filter((x) => x.kind === "show").sort((a, b) => a.date.localeCompare(b.date));
    let showsDone = false;
    for (const x of tl) {
      if (x.kind === "show") {
        if (showsDone) continue;
        showsDone = true;
        $("timeline").append(el("li", { class: "tl-show" },
          el("span", { class: "tl-date" }, `${shows[0].date.replaceAll("-", ".")} ~ ${shows[shows.length - 1].date.slice(5).replace("-", ".")}`),
          el("span", {}, t("tl_first_shows")),
          el("span", { class: "tl-chips" }, ...shows.map((s_) => el("span", { class: "chip" }, `${s_.date.slice(5).replace("-", ".")} ${tc(s_.show)}`)))));
        continue;
      }
      $("timeline").append(el("li", { class: `tl-${x.kind}` },
        el("span", { class: "tl-date" }, x.date.replaceAll("-", ".")),
        x.url ? ext(x.url, tx(x)) : el("span", {}, tx(x))));
    }
    fold($("timeline"), 5);
  } else {
    $("timelineSec").remove();
  }

  // ---------- 오늘의 직캠 (안 본 직캠 우선) ----------
  const allFancams = data.members.flatMap((m) => m.fancams);
  function pickFancam() {
    const pool = allFancams.filter((v) => !seen.has(v.id));
    const from = pool.length ? pool : allFancams;
    const v = from[Math.floor(Math.random() * from.length)];
    $("pick").replaceChildren(videoCard(v, v.member || catLabel("fancam")));
  }
  if (allFancams.length) { pickFancam(); $("pickBtn").addEventListener("click", pickFancam); }
  else $("pickSec").remove();

  // ---------- 멤버 맞히기 퀴즈 (입덕 탭) ----------
  // 멤버 사진(members.yml photo·profile_history)이 4명 이상 있으면 사진 퀴즈,
  // 없으면 직캠 장면 퀴즈 (썸네일은 이름 글씨가 있어서 영상 장면 사용, 화질 좋은 것부터 시도)
  const photoQs = data.members.flatMap((m) => [...new Set([m.photo, ...(m.profile_history || []).map((h) => h.photo)])]
    .filter(Boolean).map((src) => ({ member: m.name, photo: src })));
  const photoMode = new Set(photoQs.map((x) => x.member)).size >= 4;
  const quizPool = photoMode ? photoQs : allFancams.filter((v) => v.member).map((v) => ({ member: v.member, video: v }));
  const quizMembers = [...new Set(quizPool.map((x) => x.member))];
  if (quizPool.length >= 4 && quizMembers.length >= 4) {
    const ROUND = 10;
    let q = 0, score = 0;
    const best = () => pref.get("quizBest", 0);
    const shuffle = (a) => a.map((x) => [Math.random(), x]).sort((x, y) => x[0] - y[0]).map((x) => x[1]);
    const showScore = () => { $("quizScore").textContent = t("quiz_score", { q: Math.min(q + 1, ROUND), n: ROUND, s: score, b: best() }); };
    const frameImg = (id, n) => {
      const srcs = [`maxres${n}`, `sd${n}`, `hq${n}`].map((f) => `https://i.ytimg.com/vi/${id}/${f}.jpg`);
      const img = el("img", { class: "quiz-img", src: srcs[0], alt: "" });
      let i = 0;
      const next = () => {
        i += 1;
        if (i < srcs.length) img.src = srcs[i]; else img.closest(".quiz-cell")?.remove();
      };
      img.addEventListener("error", next);
      // 없는 화질은 120x90 회색 기본 이미지로 오는 경우가 있어서 크기로도 확인
      img.addEventListener("load", () => { if (img.naturalWidth <= 120) next(); });
      return el("div", { class: "quiz-cell" }, img);
    };
    let recentQ = [];
    function ask() {
      if (q >= ROUND) return finish();
      showScore();
      const fresh = quizPool.filter((x) => !recentQ.includes(x));
      const item = fresh[Math.floor(Math.random() * fresh.length)] || quizPool[0];
      recentQ = [...recentQ, item].slice(-Math.min(ROUND, quizPool.length - 1));
      const v = item.video || { member: item.member };
      const opts = shuffle([item.member, ...shuffle(quizMembers.filter((n) => n !== item.member)).slice(0, 3)]);
      const frames = item.photo
        ? [el("div", { class: "quiz-cell quiz-photo" }, el("img", { class: "quiz-img", src: item.photo, alt: "" }))]
        : [1, 2, 3].map((n) => frameImg(v.id, n));
      const result = el("div", { class: "quiz-result" });
      const btns = opts.map((n) => {
        const mem = data.members.find((x) => x.name === n);
        const b = el("button", { class: "quiz-opt", type: "button" }, n, mem?.ko ? el("span", { class: "muted" }, ` ${mem.ko}`) : null);
        b.addEventListener("click", () => {
          btns.forEach((x) => { x.disabled = true; });
          const ok = n === item.member;
          if (ok) score++;
          b.classList.add(ok ? "ok" : "no");
          btns[opts.indexOf(item.member)].classList.add("ok");
          const next = el("button", { class: "more", type: "button" }, q + 1 >= ROUND ? t("quiz_done") : t("quiz_next"));
          next.addEventListener("click", () => { q++; ask(); });
          result.replaceChildren(...[el("b", {}, ok ? t("quiz_ok") : t("quiz_no", { name: item.member })),
            item.video ? ext(ytUrl(item.video.id), t("quiz_watch")) : null, next].filter(Boolean));
          showScore();
        });
        return b;
      });
      $("quiz").replaceChildren(el("p", { class: "quiz-q" }, t(item.photo ? "quiz_q_photo" : "quiz_q")), el("div", { class: "quiz-frame" }, ...frames),
        el("div", { class: "quiz-opts" }, ...btns), result);
    }
    function finish() {
      if (score > best()) pref.set("quizBest", score);
      const again = el("button", { class: "more", type: "button" }, t("quiz_again"));
      again.addEventListener("click", () => { q = 0; score = 0; ask(); });
      $("quizScore").textContent = "";
      $("quiz").replaceChildren(el("div", { class: "quiz-end" },
        el("div", { class: "quiz-big" }, `${score} / ${ROUND}`),
        el("div", { class: "muted" }, t("quiz_best", { b: best() })), again));
    }
    const start = el("button", { class: "more", type: "button" }, t("quiz_start"));
    start.addEventListener("click", ask);
    $("quiz").append(el("p", { class: "note small" }, t("quiz_desc")), start);
  } else {
    $("quizSec").remove();
  }

  // ---------- 최애 (한눈에 맨 위) ----------

  let bias = pref.get("bias", "");
  function renderBias() {
    const m = data.members.find((x) => x.name === bias);
    const sel = el("select", { class: "sel", "aria-label": t("bias_pick") },
      el("option", { value: "" }, t("bias_pick")),
      ...data.members.map((x) => el("option", { value: x.name, ...(x.name === bias ? { selected: "" } : {}) }, x.ko ? `${x.name} · ${x.ko}` : x.name)));
    sel.addEventListener("change", () => setBias(sel.value));
    const head = el("div", { class: "sec-head" }, el("h2", {}, m ? t("bias_title", { name: m.name }) : t("bias_pick")), sel);
    const body = [];
    if (m) {
      const bd = upcomingBirthdays(30).find((b) => b.member === m.name);
      if (bd) body.push(el("div", { class: "bias-bd" }, bd.title));
      const vids = [...m.fancams].slice(0, 4);
      if (vids.length) body.push(el("div", { class: "videos" }, ...vids.map((v) => videoCard(v, tc(v.show) || catLabel(v.category)))));
      else body.push(empty(t("fancam_pending")));
      if ((m.ig_mentions || []).length) body.push(el("div", { class: "ig-feed bias-ig" }, ...m.ig_mentions.slice(0, 2).map((x) => igPost(x, false))));
      const more = el("button", { class: "more", type: "button" }, t("profile_view"));
      more.addEventListener("click", () => openMember(m));
      body.push(more);
    } else {
      body.push(el("p", { class: "note small" }, t("bias_desc")));
    }
    $("bias").replaceChildren(head, ...body);
  }
  function setBias(name) {
    bias = name;
    pref.set("bias", name);
    renderBias();


  }
  renderBias();

  // ---------- 헤더 사진 띠 (15명, 누르면 프로필) ----------
  const withPhoto = data.members.filter((m) => m.photo);
  if (withPhoto.length >= 5) {
    const chip = (m, dup) => {
      const b = el("button", { type: "button", class: "strip-m", ...(dup ? { "aria-hidden": "true", tabindex: "-1" } : {}) },
        el("img", { src: m.photo, alt: "", loading: "lazy" }), el("span", {}, m.name));
      b.addEventListener("click", () => openMember(m));
      return b;
    };
    // 끝없이 흐르게 같은 줄을 두 번 (두 번째는 화면 읽기에서 제외)
    $("stripTrack").append(...withPhoto.map((m) => chip(m, false)), ...withPhoto.map((m) => chip(m, true)));
    $("strip").hidden = false;
  }

  // ---------- 공식 사진 모음 (멤버 탭): 인스타·X 사진 게시물, 멤버 이름이 본문에 있으면 멤버별로 ----------
  const photos = data.photos || [];
  if (photos.length) {
    let who = "", shown = 18;
    const mems = data.members.map((m) => m.name);  // 15명 모두 (사진이 아직 없으면 '없음' 표시)
    const btn = (label, on, fn) => {
      const b = el("button", { type: "button", class: on ? "on" : "", "aria-pressed": String(on) }, label);
      b.addEventListener("click", fn);
      return b;
    };
    const draw = () => {
      $("photoMem").replaceChildren(btn(t("ev_all"), !who, () => { who = ""; shown = 18; draw(); }),
        ...mems.map((n) => {
          const c = photos.filter((x) => (x.members || []).includes(n)).length;
          return btn(c ? `${n} ${c}` : n, n === who, () => { who = n; shown = 18; draw(); });
        }));
      const list = photos.filter((x) => !who || (x.members || []).includes(who));
      if (!list.length) { $("photoGrid").replaceChildren(empty(t("photos_none"))); $("photoMore").hidden = true; return; }
      $("photoGrid").replaceChildren(...list.slice(0, shown).map((x) => {
        const img = el("img", { src: x.src, alt: x.text || "A2O SOUL", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
        const a = el("a", { href: x.url, target: "_blank", rel: "noopener", title: `${x.at} · ${x.text || ""}` }, img,
          el("span", { class: `src src-${x.account}` }, x.account === "x" ? "X" : "IG"));
        img.addEventListener("error", () => a.remove());  // 만료된 주소는 숨김
        return a;
      }));
      $("photoMore").hidden = list.length <= shown;
    };
    $("photoMore").onclick = () => { shown += 18; draw(); };
    draw();
  } else {
    $("photoSec").remove();
  }

  // ---------- 사이트 사용법: 입덕 탭 섹션 + 첫 방문 안내 + 하단 버튼 ----------
  const tourItems = (dlg) => (t("tour_items") || []).map(([ico, title, desc, tab]) => {
    const body = [el("span", { class: "tour-ico", "aria-hidden": "true" }, ico), el("b", {}, title), el("span", {}, desc),
      tab ? el("span", { class: "go" }, t("tour_go")) : null];
    if (!tab) return el("li", {}, el("div", { class: "tour-item" }, ...body));
    const a = el("a", { class: "tour-item", href: `#${tab}` }, ...body);
    a.addEventListener("click", () => { if (dlg) dlg.close(); setTimeout(() => window.scrollTo({ top: 0 }), 0); });
    return el("li", {}, a);
  });
  // 맨 위 3단계 요약 (최애 → 알림 → 홈 화면)
  const tourSteps = () => el("div", { class: "tour-steps" }, ...(t("tour_steps") || []).map((x, i) => el("div", {}, el("b", {}, String(i + 1)), el("span", {}, x))));
  $("tourList").replaceChildren(...tourItems(null));
  $("tourList").before(tourSteps());
  const tourDlg = $("tourDlg");
  $("tourDlgList").before(tourSteps());
  const openTour = () => { $("tourDlgList").replaceChildren(...tourItems(tourDlg)); tourDlg.showModal(); };
  const hideTip = () => { $("tourTip").hidden = true; pref.set("tourSeen", true); };
  $("tourClose").onclick = () => tourDlg.close();
  $("tourNever").onclick = () => { hideTip(); tourDlg.close(); };
  tourDlg.addEventListener("click", (e) => { if (e.target === tourDlg) tourDlg.close(); });
  $("tourOpen").onclick = openTour;
  $("tourX").onclick = hideTip;
  $("tourFoot").onclick = openTour;
  if (!pref.get("tourSeen", false)) $("tourTip").hidden = false;

  // ---------- 웹 푸시 알림 (🔔 알림 받기) ----------
  {
    const cfg = data.push || {};
    const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    const ios = /iP(hone|ad|od)/.test(navigator.userAgent);
    const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    if (cfg.api && cfg.vapid_public && (supported || ios)) {
      const TOPICS = ["notice", "vote", "show", "video"];
      const dlg = $("pushDlg"), btn = $("pushBtn");
      const keyBytes = (b64) => Uint8Array.from(atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64.length + 3) % 4)), (c) => c.charCodeAt(0));
      const getSub = async () => (supported ? (await navigator.serviceWorker.ready).pushManager.getSubscription() : null);
      const mark = (on) => btn.classList.toggle("on", !!on);
      btn.hidden = false;
      getSub().then(mark).catch(() => {});
      const render = async (msg) => {
        const sub = await getSub().catch(() => null);
        const body = [];
        if (!supported || (ios && !standalone)) {
          body.push(el("p", {}, t("push_ios")));
          const b = el("button", { type: "button", class: "more" }, t("ios_title"));
          b.onclick = () => { dlg.close(); $("installHelp").showModal(); };
          body.push(b);
        } else {
          const chosen = new Set(pref.get("pushTopics", TOPICS));
          body.push(el("p", { class: "muted small" }, t("push_desc")));
          body.push(el("div", { class: "push-topics" }, ...TOPICS.map((k) => {
            const cb = el("input", { type: "checkbox", value: k, ...(chosen.has(k) ? { checked: "" } : {}) });
            cb.onchange = () => (cb.checked ? chosen.add(k) : chosen.delete(k));
            return el("label", {}, cb, " ", t(`push_t_${k}`));
          })));
          const on = el("button", { type: "button", class: "install" }, sub ? t("push_save") : t("push_on"));
          on.onclick = async () => {
            on.disabled = true;
            try {
              if ((await Notification.requestPermission()) !== "granted") return render(t("push_denied"));
              const reg = await navigator.serviceWorker.ready;
              const s = (await reg.pushManager.getSubscription()) ||
                (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(cfg.vapid_public) }));
              const topics = TOPICS.filter((k) => chosen.has(k));
              const r = await fetch(cfg.api.replace(/\/$/, "") + "/subscribe", { method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sub: s.toJSON(), topics, lang: LANG }) });
              if (!r.ok) throw new Error(r.status);
              pref.set("pushTopics", topics);
              mark(true);
              render(t("push_ok"));
            } catch (_) {
              render(t("push_fail"));
            }
          };
          const row = el("div", { class: "push-actions" }, on);
          if (sub) {
            const off = el("button", { type: "button", class: "more" }, t("push_off"));
            off.onclick = async () => {
              try { await fetch(cfg.api.replace(/\/$/, "") + "/unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: sub.endpoint }) }); } catch (_) { /* 무시 */ }
              await sub.unsubscribe().catch(() => {});
              mark(false);
              render(t("push_off_ok"));
            };
            row.append(off);
          }
          body.push(row, el("p", { class: "muted small" }, t("push_delay")));
        }
        if (msg) body.unshift(el("p", { class: "push-msg", role: "status" }, msg));
        $("pushBody").replaceChildren(...body);
      };
      btn.onclick = () => { render(); dlg.showModal(); };
      $("pushClose").onclick = () => dlg.close();
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    }
  }

  // ---------- 포토카드 (입덕 탭): site/img/photocards/버전_라벨_멤버.webp ----------
  const pcs = data.photocards || [];
  const pcCredit = (data.info || {}).photocard_credit || {};
  const pcCreditLine = () => (pcCredit.url
    ? el("p", { class: "pf-src" }, t("pc_credit"), " ", ext(pcCredit.url, pcCredit.label || pcCredit.url)) : null);
  const pcCard = (x, list, i) => pcBtn(x, list, i, el("span", { class: "pc-cap" }, x.member,
    x.label ? el("span", { class: "muted" }, ` · ${x.label}`) : null));
  if (pcs.length) {
    const versions = [...new Set(pcs.map((x) => x.version))];
    const mems = [...new Set(pcs.map((x) => x.member))].sort((a, b) => (a === bias ? -1 : b === bias ? 1 : 0));
    let pcVer = versions[0];
    let pcWho = "";
    const btn = (label, on, fn) => {
      const b = el("button", { type: "button", class: on ? "on" : "", "aria-pressed": String(on) }, label);
      b.addEventListener("click", fn);
      return b;
    };
    // 멤버를 고르면 '전체'(모든 버전을 버전별 묶음으로)가 기본 — 멤버 전체에서 '전체'는 너무 많아서 버전 하나씩
    const drawPc = () => {
      const inWho = pcs.filter((x) => !pcWho || x.member === pcWho);
      if (!pcWho && pcVer === "") pcVer = versions[0];
      $("pcTabs").replaceChildren(
        ...(pcWho ? [btn(`${t("ev_all")} ${inWho.length}`, pcVer === "", () => { pcVer = ""; drawPc(); })] : []),
        ...versions.map((v) => btn(`${tc(v)} ${inWho.filter((x) => x.version === v).length}`, v === pcVer,
          () => { pcVer = v; drawPc(); })));
      $("pcMem").replaceChildren(btn(t("ev_all"), !pcWho, () => { pcWho = ""; drawPc(); }),
        ...mems.map((m) => btn(m, m === pcWho, () => { pcWho = m; pcVer = ""; drawPc(); })));
      if (pcVer === "") {
        $("pcGrid").replaceChildren(...versions.filter((v) => inWho.some((x) => x.version === v)).map((v) => {
          const list = inWho.filter((x) => x.version === v);
          return el("div", { class: "pc-group" }, el("h4", { class: "pc-group-h" }, tc(v)),
            el("div", { class: "pc-grid" }, ...list.map((x, i) => pcCard(x, list, i))));
        }));
        $("pcGrid").classList.add("pc-all");
        fold($("pcGrid"), 99);  // 이전 '더 보기' 버튼 지우기
        return;
      }
      $("pcGrid").classList.remove("pc-all");
      const list = inWho.filter((x) => x.version === pcVer);
      $("pcGrid").replaceChildren(...(list.length ? list.map((x, i) => pcCard(x, list, i)) : [el("p", { class: "muted" }, "—")]));
      fold($("pcGrid"), MOBILE ? 12 : 24);
    };
    drawPc();
    $("pcCredit").replaceWith(Object.assign(pcCreditLine() || el("p"), { id: "pcCredit" }));
  } else {
    $("pcSec").remove();
  }

  // ---------- 차트 ----------
  const palette = ["#6c4cf5", "#f5734c", "#12a1a0", "#e0479e", "#d4a017", "#3b82f6", "#8b5cf6", "#22c55e"];
  if (window.Chart) {
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.color = css.getPropertyValue("--muted").trim();
    Chart.defaults.borderColor = css.getPropertyValue("--line").trim();
    Chart.defaults.font.family = "Pretendard, sans-serif";
  }
  const tooltip = { callbacks: { label: (c) => `${c.dataset.label ?? ""}${c.dataset.label ? ": " : ""}${fmt(c.parsed.y ?? c.parsed.x)}` } };

  // 가로축 날짜는 짧게 (2026-11-14 → 11/14), 툴팁엔 전체 날짜
  const xDate = { ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 8, callback(v) {
    const l = String(this.getLabelForValue(v));
    return /^\d{4}-\d{2}-\d{2}$/.test(l) ? `${+l.slice(5, 7)}/${+l.slice(8, 10)}` : l;
  } } };

  function lineChart(id, seriesList) {
    const canvas = $(id);
    const labels = [...new Set(seriesList.flatMap((s) => s.points.map((p) => p[0])))].sort();
    if (!labels.length) { canvas.parentElement.replaceWith(empty(t("empty_chart"))); return; }
    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: seriesList.map((s, i) => {
          const m = Object.fromEntries(s.points);
          const c = palette[i % palette.length];
          return { label: s.name ?? s.title, data: labels.map((l) => m[l] ?? null), spanGaps: true,
                   borderColor: c, backgroundColor: c, tension: 0.25, pointRadius: 2 };
        }),
      },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                 scales: { x: xDate, y: { ticks: { callback: fmt } } }, plugins: { tooltip } },
    });
  }

  function dailyChart(id, seriesList) {
    const canvas = $(id);
    const diffs = seriesList.map((s) => {
      const out = {};
      for (let i = 1; i < s.points.length; i++) out[s.points[i][0]] = s.points[i][1] - s.points[i - 1][1];
      return { name: s.title, out };
    });
    const labels = [...new Set(diffs.flatMap((d) => Object.keys(d.out)))].sort();
    if (!labels.length) { canvas.parentElement.replaceWith(empty(t("empty_daily"))); return; }
    new Chart(canvas, {
      type: "bar",
      data: { labels, datasets: diffs.map((d, i) => ({ label: d.name, data: labels.map((l) => d.out[l] ?? null),
                                                         backgroundColor: palette[i % palette.length], borderRadius: 4 })) },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                 scales: { x: { ...xDate, stacked: true }, y: { stacked: true, ticks: { callback: fmt } } }, plugins: { tooltip } },
    });
  }

  function rankCharts() {
    const canvases = [...$("charts").querySelectorAll("canvas")];
    (data.charts || []).filter((c) => c.ranks.length > 1).forEach((c, i) => {
      new Chart(canvases[i], {
        type: "line",
        data: { labels: c.ranks.map((r) => r[0].slice(5)),
                datasets: [{ data: c.ranks.map((r) => r[1]), borderColor: palette[i % palette.length], backgroundColor: palette[i % palette.length], tension: 0.2, pointRadius: 2 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false },
                   tooltip: { callbacks: { label: (x) => t("rank", { n: x.parsed.y }) } } },
                   scales: { y: { reverse: true, ticks: { precision: 0 } } } },
      });
    });
  }

  drawers.overview = () => lineChart("accountsChart", data.accounts);
  drawers.cheer = rankCharts;
  drawers.mv = () => { lineChart("mvChart", data.mvs); dailyChart("mvDailyChart", data.mvs); };

  openRoute = () => {
    const [head, a, b, c, d] = route();
    if (head === "member") {
      const m = data.members.find((x) => x.name.toLowerCase() === (a || "").toLowerCase() || x.ko === a);
      if (m && !dlg.open) openMember(m);
    } else if (head === "ep") {
      const box = document.getElementById(`ep-${a}-${b}`);
      if (box) { box.open = true; setTimeout(() => box.scrollIntoView({ block: "start" }), 50); }
    } else if (head === "cmp") {
      const x = cmpEps.find((e) => e.ep.date === a && e.ep.show === b);
      if (x && !cmpDlg.open) openCompare(x.ep, x.cams, [c, d]);
    }
  };
  showTab();
  openRoute();
})();
