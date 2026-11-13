// ---------- 언어 ----------
const LANGS = ["ko", "en", "ja", "zh", "es", "id", "th"];
const LOCALES = { ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN", es: "es-ES", id: "id-ID", th: "th-TH" };
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
document.documentElement.lang = LANG;
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
  const kstFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" });
  const todayKst = kstFmt.format(new Date()); // YYYY-MM-DD
  const nat = (s) => (s || "").split("·").map((x) => (t("nat")[x] || x)).join("·");
  // 내용 번역 (translations.yml): 한국어 원문 그대로 키, 없으면 원문
  let TR = {};
  const tc = (s) => (LANG === "ko" || !s ? s : TR[s]?.[LANG] || s);
  // 자동으로 만든 문구(기록·기념일)는 언어별 틀로
  const tx = (x) => {
    if (x.key) return t(x.key, { n: x.key.startsWith("anniv") ? x.n : fmt(x.n), show: tc(x.show), type: tc(x.type), name: x.name });
    const m = /^(.+) 출연$/.exec(x.title || ""); // 공지에서 뽑은 '뮤직뱅크 출연'
    return m ? t("ev_show", { show: tc(m[1]) }) : tc(x.title);
  };
  const kstDate = (s) => new Date(`${s.replace(" ", "T")}${s.length > 10 ? ":00" : "T00:00:00"}+09:00`); // "YYYY-MM-DD[ HH:MM]" KST

  // ---------- 탭 ----------
  const tabs = ["overview", "cheer", "mv", "members", "fancams", "videos", "guide"];
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
  const voteEvents = (data.votes || []).map((v) => ({
    date: v.end.slice(0, 10), time: v.end.slice(11), type: t("votes"),
    title: `🗳 ${[tc(v.show), tc(v.title)].filter(Boolean).join(" ")}`, url: v.url,
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
  const allEvents = [...(data.events || []).filter((e) => e.date >= todayKst), ...upcomingBirthdays(), ...voteEvents, ...supportEvents]
    .map((e) => {
      const show = /^(.+) 출연$/.exec(e.title || "")?.[1];
      return { ...e, group: groupOf(e), time: e.time || (show && showTime[show]) || e.time };
    })
    .sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
  // 달력에 넣을 생일은 보는 달 기준으로 (목록은 30일 이내만)
  const birthdaysIn = (y, mo) => (data.members || []).filter((m) => (m.birthday || "").startsWith(String(mo).padStart(2, "0") + "-"))
    .map((m) => ({ date: `${y}-${m.birthday}`, type: t("ev.birthday"), title: `🎂 ${t("ev.birthday")} · ${m.name}`, member: m.name, group: "anniv" }));
  const EV_GROUPS = [["all", "ev_all"], ["show", "ev_show_g"], ["anniv", "ev_anniv_g"], ["etc", "ev_etc_g"]];
  let evGroup = pref.get("evGroup", "all");
  let evView = pref.get("evView", "cal");
  const todayD = new Date(`${todayKst}T00:00:00Z`);
  let calY = todayD.getUTCFullYear(), calM = todayD.getUTCMonth() + 1, calSel = todayKst;
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
      ` (${wd[d.getUTCDay()]})`, e.time ? ` ${e.time}` : null);
    let title;
    if (e.member) {
      title = el("button", { type: "button", class: "linklike" }, e.title);
      const mem = data.members.find((x) => x.name === e.member);
      title.addEventListener("click", () => openMember(mem));
    } else {
      title = e.url ? ext(e.url, tx(e)) : el("span", {}, tx(e));
    }
    title.classList.add("what");
    return el("li", { class: `ev-${e.group}` }, whenEl, el("div", {}, e.type ? el("span", { class: "chip" }, tc(e.type)) : null, title));
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
    for (let i = 0; i < first.getUTCDay(); i++) grid.append(el("div", { class: "cal-cell empty" }));
    for (let d = 1; d <= days; d++) {
      const iso = `${calY}-${String(calM).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const list = byDay[iso] || [];
      const groups = [...new Set(list.map((e) => e.group))];
      const cell = el("button", { type: "button", class: `cal-cell${iso === todayKst ? " today" : ""}${iso === calSel ? " sel" : ""}${iso < todayKst ? " past" : ""}`,
        "aria-label": `${iso} ${list.length}` },
        el("span", { class: "cal-d" }, String(d)),
        el("span", { class: "cal-dots" }, ...groups.map((g) => el("i", { class: `dot dot-${g}` }))));
      cell.addEventListener("click", () => { calSel = iso; renderCal(); });
      grid.append(cell);
    }
    // 고른 날 일정, 없으면 이 달 남은 일정
    const sel = calSel ? (byDay[calSel] || []) : [];
    const rest = evs.filter((e) => e.date >= (calSel || todayKst)).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
    const list = calSel && sel.length ? sel : rest.slice(0, 6);
    calBox.replaceChildren(
      el("div", { class: "cal-head" }, prev, el("b", {}, monthName), next),
      grid,
      el("div", { class: "cal-sub muted small" }, calSel && sel.length ? "" : t("cal_upcoming")),
      el("ul", { class: "events" }, ...(list.length ? list.map(evItem) : [el("li", { class: "empty" }, "–")])));
  }

  function renderEvents() {
    evTabs.replaceChildren(...EV_GROUPS.filter(([k]) => k === "all" || allEvents.some((e) => e.group === k)).map(([k, label]) => {
      const n = k === "all" ? allEvents.length : allEvents.filter((e) => e.group === k).length;
      const b = el("button", { type: "button", class: k === evGroup ? "on" : "" }, `${t(label)} ${n}`);
      b.addEventListener("click", () => { evGroup = k; pref.set("evGroup", k); renderEvents(); });
      return b;
    }));
    viewBtn.textContent = evView === "cal" ? `☰ ${t("ev_list")}` : `📅 ${t("ev_cal")}`;
    if (evView === "cal") {
      $("events").hidden = true; calBox.hidden = false; renderCal();
    } else {
      calBox.hidden = true; $("events").hidden = false;
      const list = allEvents.filter(pass).slice(0, 10);
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
  const votes = (data.votes || []).filter((v) => kstDate(v.end) > Date.now());
  if (votes.length) {
    for (const v of votes) {
      const start = kstDate(v.start), end = kstDate(v.end);
      const open = Date.now() >= start;
      const urgent = open && end - Date.now() < 6 * 3600000;
      $("votes").append(el("div", { class: `vote${urgent ? " urgent" : ""}` },
        el("div", { class: "vote-top" },
          el("span", { class: `chip ${open ? "chip-on" : ""}` }, open ? t("vote_now") : t("vote_soon")),
          el("b", {}, [tc(v.show), tc(v.title)].filter(Boolean).join(" · ")), v.app ? el("span", { class: "muted" }, ` · ${tc(v.app)}`) : null),
        el("div", { class: "vote-time" }, open ? t("vote_ends", { t: duration(end - Date.now()) }) : t("vote_starts", { t: duration(start - Date.now()) }),
          el("span", { class: "muted" }, ` · ${t("vote_end_at", { t: v.end.slice(5).replace("-", ".") })}`)),
        v.note ? el("div", { class: "muted small" }, tc(v.note)) : null,
        el("div", { class: "vote-links" }, v.url ? ext(v.url, t("vote_open")) : null,
          v.source && v.source !== v.url ? ext(v.source, t("from_notice"), " ↗") : null)));
    }
  } else {
    $("votes").append(empty(t("no_votes")));
  }

  if ((data.streaming || []).length) {
    for (const s of data.streaming) {
      $("streaming").append(el("li", {},
        el("div", {}, el("b", {}, s.title), s.note ? el("span", { class: "muted" }, ` · ${tc(s.note)}`) : null),
        Object.keys(s.links).length ? el("div", { class: "links small" }, ...Object.entries(s.links).map(([k, u]) => ext(u, k))) : null));
    }
  } else {
    $("streaming").closest("section").remove();
  }

  const howto = data.howto || {};
  if ((howto.voting || []).length || (howto.streaming || []).length) {
    if ((howto.voting || []).length) {
      const box = el("details", { class: "howto", open: "" }, el("summary", {}, t("howto_voting")));
      for (const v of howto.voting) {
        box.append(el("div", { class: "howto-show" },
          el("div", {}, el("b", {}, tc(v.show)), v.when ? el("span", { class: "muted" }, ` · ${tc(v.when)}`) : null),
          el("div", { class: "howto-apps" },
            v.pre ? el("span", {}, el("span", { class: "chip" }, t("howto_pre")), ` ${tc(v.pre)}`) : null,
            v.live ? el("span", {}, el("span", { class: "chip chip-on" }, t("howto_live")), ` ${tc(v.live)}`) : null),
          v.note ? el("div", { class: "muted small" }, tc(v.note)) : null,
          v.url ? ext(v.url, "↗ link") : null));
      }
      $("howto").append(box);
    }
    for (const g of howto.streaming || []) {
      $("howto").append(el("details", { class: "howto" }, el("summary", {}, tc(g.title)),
        el("ol", { class: "howto-steps" }, ...g.steps.map((x) => el("li", {}, tc(x))))));
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

  const notices = data.notices || [];
  const shops = data.info?.shops || [];
  for (const x of shops) $("shops").append(ext(x.url, tc(x.label), x.note ? el("span", { class: "muted" }, ` · ${tc(x.note)}`) : null));
  if (!shops.length) $("shops").remove();
  if (notices.length || shops.length) {
    for (const x of notices) {
      const when = [x.date ? x.date.slice(5).replace("-", ".") : "", x.time || "",
        x.end_date && x.end_date !== x.date ? `~ ${x.end_date.slice(5).replace("-", ".")}` : ""].filter(Boolean).join(" ");
      $("notices").append(el("div", { class: "support" },
        el("div", {}, el("span", { class: "chip" }, x.label), el("b", {}, x.title)),
        when || x.place ? el("div", { class: "muted" }, [when, x.place].filter(Boolean).join(" · ")) : null,
        el("div", { class: "links small" }, x.url ? ext(x.url, "↗ link") : null, x.post ? ext(x.post, `${t("from_notice")} ↗`) : null)));
    }
  } else {
    $("noticesSec").remove();
  }

  // ---------- 공식 인스타 피드 ----------
  const igPost = (x, withMembers = true) => {
    const iso = x.at ? kstDate(x.at).toISOString() : null;
    return el("a", { class: "ig-post", href: x.url, target: "_blank", rel: "noopener" },
      el("div", { class: "ig-meta" }, ageHours(iso) <= NEW_HOURS ? el("span", { class: "chip chip-on" }, "NEW") : null,
        el("span", { class: "muted" }, iso ? when(iso) : ""),
        x.likes != null ? el("span", { class: "muted" }, `♥ ${fmt(x.likes)}`) : null,
        x.comments != null ? el("span", { class: "muted" }, `💬 ${fmt(x.comments)}`) : null),
      el("div", { class: "ig-text" }, (x.text || "") + (x.more ? "…" : "")),
      withMembers && (x.members || []).length ? el("div", { class: "ig-members" }, ...x.members.map((n) => el("span", { class: "chip" }, n))) : null);
  };
  const feed = data.ig_feed || [];
  if (feed.length) {
    feed.slice(0, 5).forEach((x) => $("igFeed").append(igPost(x)));
    if (feed.length > 5) {
      $("igMore").hidden = false;
      $("igMore").onclick = () => { feed.slice(5).forEach((x) => $("igFeed").append(igPost(x))); $("igMore").remove(); };
    }
  } else {
    $("igFeedSec").remove();
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
  const PAGE = 24;
  const cur = { cat: "all", fmt: "all", q: "", series: "", show: "", era: "", unseen: false };
  let shown = 0;
  const chipOf = (v) => (v.predebut ? catLabel("predebut") : v.member || v.series || catLabel(v.category));
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
  if (chants.length) $("fanchants").append(...chants.map((v) => videoCard(v, v.song || null)));
  else $("fanchantSec").remove();

  // ---------- 음방 회차별 무대 (영상 탭) ----------
  const eps = data.episodes || [];
  if (eps.length) {
    const wd = t("weekdays");
    for (const ep of eps) {
      const day = wd[new Date(`${ep.date}T12:00:00Z`).getUTCDay()];
      const grid = el("div", { class: "videos" });
      const box = el("details", { class: "howto ep", id: `ep-${ep.date}-${ep.show}` },
        el("summary", {}, el("span", {}, el("b", {}, `${ep.date.slice(5).replace("-", ".")} (${day}) ${tc(ep.show)}`),
          el("span", { class: "muted" }, ` · ${ep.ep ? `EP.${ep.ep} · ` : ""}${t("videos_n", { n: ep.videos.length })}`))),
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
        grid.append(...ep.videos.map((v) => videoCard(v, v.member || (v.category === "fancam" ? catLabel("fancam") : catLabel("stage")))));
      });
      $("episodes").append(box);
    }
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
      const sel = el("select", { class: "sel", "aria-label": `${t("cmp_open")} ${i + 1}` }, ...cams.map((v, j) => el("option", { value: j, ...(j === want[i] ? { selected: "" } : {}) }, v.member)));
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
    $("cmpBody").replaceChildren(el("p", { class: "note small" }, t("cmp_desc")),
      el("div", { class: "cmp-pick" }, slots[0].sel, el("span", { class: "muted" }, "vs"), slots[1].sel), go,
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
  const tl = data.timeline || [];
  if (tl.length) {
    for (const x of tl) {
      $("timeline").append(el("li", { class: `tl-${x.kind}` },
        el("span", { class: "tl-date" }, x.date.replaceAll("-", ".")),
        x.url ? ext(x.url, tx(x)) : el("span", {}, tx(x))));
    }
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

  // ---------- 차트 ----------
  const palette = ["#6c4cf5", "#f5734c", "#12a1a0", "#e0479e", "#d4a017", "#3b82f6", "#8b5cf6", "#22c55e"];
  if (window.Chart) {
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.color = css.getPropertyValue("--muted").trim();
    Chart.defaults.borderColor = css.getPropertyValue("--line").trim();
    Chart.defaults.font.family = "Pretendard, sans-serif";
  }
  const tooltip = { callbacks: { label: (c) => `${c.dataset.label ?? ""}${c.dataset.label ? ": " : ""}${fmt(c.parsed.y ?? c.parsed.x)}` } };

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
                 scales: { y: { ticks: { callback: fmt } } }, plugins: { tooltip } },
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
                 scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: fmt } } }, plugins: { tooltip } },
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
