// ---------- 언어 ----------
const LANGS = ["ko", "en", "ja", "zh", "es", "id"];
const LOCALES = { ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN", es: "es-ES", id: "id-ID" };
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
  const ext = (href, ...children) => el("a", { href, target: "_blank", rel: "noopener" }, ...children);
  const empty = (msg) => el("div", { class: "empty" }, msg);
  const kstFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" });
  const todayKst = kstFmt.format(new Date()); // YYYY-MM-DD
  const nat = (s) => (s || "").split("·").map((x) => (t("nat")[x] || x)).join("·");
  const kstDate = (s) => new Date(`${s.replace(" ", "T")}${s.length > 10 ? ":00" : "T00:00:00"}+09:00`); // "YYYY-MM-DD[ HH:MM]" KST

  // ---------- 탭 ----------
  const tabs = ["overview", "cheer", "mv", "members", "fancams", "videos", "guide"];
  const drawn = new Set();
  const drawers = {};
  function showTab() {
    const cur = tabs.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
    document.querySelectorAll("[data-tab]").forEach((s) => (s.hidden = s.dataset.tab !== cur));
    document.querySelectorAll("#tabs a").forEach((a) => {
      const on = a.getAttribute("href") === `#${cur}`;
      a.classList.toggle("on", on);
      if (on) a.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    if (!drawn.has(cur) && drawers[cur] && window.Chart) { drawn.add(cur); drawers[cur](); }
  }
  window.addEventListener("hashchange", showTab);

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
    title: `🗳 ${[v.show, v.title].filter(Boolean).join(" ")}`, url: v.url,
  }));
  const supportEvents = (data.supports || []).filter((x) => x.start >= todayKst).map((x) => ({
    date: x.start, type: x.kind, title: `☕ ${[x.member, x.title].filter(Boolean).join(" ")}`, url: x.url,
  }));
  const events = [...(data.events || []).filter((e) => e.date >= todayKst), ...upcomingBirthdays(), ...voteEvents, ...supportEvents]
    .sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || ""))).slice(0, 10);
  if (events.length) {
    const wd = t("weekdays");
    for (const e of events) {
      const d = new Date(`${e.date}T00:00:00Z`);
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
        title = e.url ? ext(e.url, e.title) : el("span", {}, e.title);
      }
      title.classList.add("what");
      $("events").append(el("li", {}, whenEl, el("div", {}, e.type ? el("span", { class: "chip" }, e.type) : null, title)));
    }
  } else {
    $("events").replaceWith(empty("–"));
  }

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
          el("b", {}, [v.show, v.title].filter(Boolean).join(" · ")), v.app ? el("span", { class: "muted" }, ` · ${v.app}`) : null),
        el("div", { class: "vote-time" }, open ? t("vote_ends", { t: duration(end - Date.now()) }) : t("vote_starts", { t: duration(start - Date.now()) }),
          el("span", { class: "muted" }, ` · ${t("vote_end_at", { t: v.end.slice(5).replace("-", ".") })}`)),
        v.url ? ext(v.url, t("vote_open")) : null));
    }
  } else {
    $("votes").append(empty(t("no_votes")));
  }

  if ((data.streaming || []).length) {
    for (const s of data.streaming) {
      $("streaming").append(el("li", {},
        el("div", {}, el("b", {}, s.title), s.note ? el("span", { class: "muted" }, ` · ${s.note}`) : null),
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
          el("div", {}, el("b", {}, v.show), v.when ? el("span", { class: "muted" }, ` · ${v.when}`) : null),
          el("div", { class: "howto-apps" },
            v.pre ? el("span", {}, el("span", { class: "chip" }, t("howto_pre")), ` ${v.pre}`) : null,
            v.live ? el("span", {}, el("span", { class: "chip chip-on" }, t("howto_live")), ` ${v.live}`) : null),
          v.note ? el("div", { class: "muted small" }, v.note) : null,
          v.url ? ext(v.url, "↗ link") : null));
      }
      $("howto").append(box);
    }
    for (const g of howto.streaming || []) {
      $("howto").append(el("details", { class: "howto" }, el("summary", {}, g.title),
        el("ol", { class: "howto-steps" }, ...g.steps.map((x) => el("li", {}, x)))));
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
  for (const x of shops) $("shops").append(ext(x.url, x.label, x.note ? el("span", { class: "muted" }, ` · ${x.note}`) : null));
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
  if ((info.lore || []).length) for (const p of info.lore) $("lore").append(el("p", {}, p));
  else $("loreSec").remove();
  if ((info.albums || []).length) {
    for (const a of info.albums) {
      $("albums").append(el("div", { class: "album" },
        el("div", {}, el("b", {}, a.title), a.type ? el("span", { class: "muted" }, ` · ${a.type}`) : null),
        a.date ? el("div", { class: "muted small" }, [a.date.replaceAll("-", "."), a.time].filter(Boolean).join(" ") + " KST") : null,
        a.tracks.length ? el("ol", { class: "tracks" }, ...a.tracks.map((x) => el("li", {}, x))) : null,
        a.versions.length ? el("div", { class: "small" }, el("span", { class: "chip" }, t("album_versions")), a.versions.join(" · ")) : null,
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
  const facts = (m, withBday) => [m.position, m.birth_year ? t("born", { y: m.birth_year }) : "",
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
      m.nicknames.length ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("nickname")), el("div", {}, m.nicknames.join(", "))) : null,
      tip ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, "Tip"), el("div", {}, tip)) : null,
      list(t("career"), m.career),
      list(t("notes"), m.notes),
      m.signature ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("signature")),
        el("img", { class: "pf-sign", src: m.signature, alt: "", loading: "lazy" })) : null,
      (m.profile_history || []).length ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, t("history")),
        el("div", { class: "pf-history" }, ...m.profile_history.map((h) => el("figure", {},
          h.photo ? el("img", { src: h.photo, alt: h.label, loading: "lazy" }) : igEmbeds([h.instagram])[0],
          h.label ? el("figcaption", {}, h.label) : null)))) : null);
  }

  const avatar = (m, cls = "avatar") => el("div", { class: cls, "aria-hidden": "true" },
    m.photo ? el("img", { src: m.photo, alt: "", loading: "lazy" }) : (m.ko ? m.ko[0] : m.name[0]));

  function openMember(m, focus) {
    const star = el("button", { class: `bias-btn${bias === m.name ? " on" : ""}`, type: "button" },
      bias === m.name ? `★ ${t("bias_on")}` : `☆ ${t("bias_set")}`);
    star.addEventListener("click", () => {
      setBias(bias === m.name ? "" : m.name);
      star.classList.toggle("on", bias === m.name);
      star.textContent = bias === m.name ? `★ ${t("bias_on")}` : `☆ ${t("bias_set")}`;
    });
    $("dlgTitle").replaceChildren(avatar(m, "avatar dlg-avatar"), el("span", {}, m.name),
      m.ko ? el("span", { class: "dlg-ko" }, m.ko) : null, star);
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
    dlg.showModal();
    dlg.scrollTop = 0;
    if (focus) $(`dlg-${focus}`)?.scrollIntoView();
  }

  for (const l of data.group_links || []) $("groupLinks").append(ext(l.url, l.label, " ↗"));
  if (!(data.group_links || []).length) $("groupLinks").closest("section").remove();
  const gp = igEmbeds(data.group_posts);
  if (gp.length) $("groupPosts").append(...gp); else $("groupPostsSec").remove();
  $("membersHead").textContent = t("members_n", { n: data.members.length });
  for (const m of data.members) {
    const card = el("button", { class: "pcard", type: "button" },
      avatar(m),
      el("div", { class: "pinfo" },
        el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.ko)),
        el("div", { class: "s" }, facts(m, false)),
        m.nicknames.length ? el("div", { class: "s" }, t("nick_line", { v: m.nicknames.join(", ") })) : null,
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
      el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.position || nat(m.nationality))),
      tip ? el("div", { class: "s tip" }, tip) : (v ? el("div", { class: "t" }, v.title) : null),
      v ? el("div", { class: "s" }, `${ymd(v.published_at)} · ${t("views", { v: kr(v.views ?? 0) })}`) : null,
      links.length ? el("div", { class: "s more-link" }, links.map((l) => l[1]).join(" · ") + t("view")) : null);
    card.addEventListener("click", () => openMember(m, links[0]?.[0]));
    return card;
  }
  for (const m of data.members) $("members").append(fancamCard(m));
  for (const m of data.members) $("guideMembers").append(fancamCard(m));

  const course = data.guide?.course || [];
  if (course.length) {
    course.forEach((c, i) => $("course").append(el("li", {},
      el("span", { class: "step" }, String(i + 1)),
      el("div", { class: "course-card" }, c.note ? el("div", { class: "course-note" }, c.note) : null,
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
  const cur = { cat: "all", fmt: "all", q: "", series: "", show: "", unseen: false };
  let shown = 0;
  const chipOf = (v) => (v.predebut ? catLabel("predebut") : v.member || v.series || catLabel(v.category));
  const pick = (defs, key) => defs.find((d) => d[0] === key)[1];
  const norm = (s) => (s || "").toLowerCase().normalize("NFKC");
  const base = (v) => (!cur.q || norm(v.title).includes(norm(cur.q)) || norm(v.member).includes(norm(cur.q)))
    && (!cur.series || v.series === cur.series) && (!cur.show || v.show === cur.show) && (!cur.unseen || !seen.has(v.id));
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
    sel.append(el("option", { value: "" }, allLabel), ...values.map((x) => el("option", { value: x }, x)));
    sel.addEventListener("change", () => { cur[slot] = sel.value; refresh(); });
    if (!values.length) sel.hidden = true;
  }
  const uniq = (arr) => [...new Set(arr.filter(Boolean))];
  fillSelect($("seriesSel"), t("series_all"), uniq(data.videos.map((v) => v.series)).sort(), "series");
  fillSelect($("showSel"), t("show_all"), uniq(data.videos.map((v) => v.show)).sort(), "show");
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
      const box = el("details", { class: "howto ep" },
        el("summary", {}, el("span", {}, el("b", {}, `${ep.date.slice(5).replace("-", ".")} (${day}) ${ep.show}`),
          el("span", { class: "muted" }, ` · ${ep.ep ? `EP.${ep.ep} · ` : ""}${t("videos_n", { n: ep.videos.length })}`))),
        grid);
      // 펼칠 때 카드 만들기 (썸네일을 한꺼번에 불러오지 않게)
      box.addEventListener("toggle", () => {
        if (box.open && !grid.childElementCount) grid.append(...ep.videos.map((v) => videoCard(v, v.member || (v.category === "fancam" ? catLabel("fancam") : catLabel("stage")))));
      });
      $("episodes").append(box);
    }
  } else {
    $("episodesSec").remove();
  }

  // ---------- 기록 (입덕 탭) ----------
  const tl = data.timeline || [];
  if (tl.length) {
    for (const x of tl) {
      $("timeline").append(el("li", { class: `tl-${x.kind}` },
        el("span", { class: "tl-date" }, x.date.replaceAll("-", ".")),
        x.url ? ext(x.url, x.title) : el("span", {}, x.title)));
    }
  } else {
    $("timelineSec").remove();
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
      if (vids.length) body.push(el("div", { class: "videos" }, ...vids.map((v) => videoCard(v, v.show || catLabel(v.category)))));
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

  showTab();
})();
