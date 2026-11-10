(async function () {
  const fmt = (v) => (v == null ? "–" : Number(v).toLocaleString("ko-KR"));
  const kr = (n) => (n >= 1e8 ? `${+(n / 1e8).toFixed(2)}억` : n >= 1e4 ? `${+(n / 1e4).toFixed(1)}만` : fmt(n));
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
  const ext = (href, ...children) => el("a", { href, target: "_blank", rel: "noopener" }, ...children);
  const empty = (msg) => el("div", { class: "empty" }, msg);
  const todayKst = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date()); // YYYY-MM-DD

  // ---------- 탭 ----------
  const tabs = ["overview", "mv", "members", "fancams", "videos"];
  const drawn = new Set();
  const drawers = {};
  function showTab() {
    const cur = tabs.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
    document.querySelectorAll("[data-tab]").forEach((s) => (s.hidden = s.dataset.tab !== cur));
    document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${cur}`));
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
  if (!data) { $("updated").textContent = "데이터를 불러오지 못했어요"; return; }

  // ---------- 헤더 ----------
  if (data.debut_date) {
    const days = Math.round((Date.parse(todayKst) - Date.parse(data.debut_date)) / 86400000) + 1;
    $("dday").textContent = `D+${days}`;
    $("debut").textContent = `데뷔 ${data.debut_date.replaceAll("-", ".")}`;
  }
  $("updated").textContent = data.updated_at
    ? `마지막 수집: ${data.updated_at.slice(0, 16).replace("T", " ")} KST`
    : "아직 수집 전";

  // ---------- 한눈에 ----------
  for (const k of data.kpis) {
    $("kpis").append(el("div", { class: "card kpi" },
      el("div", { class: "label" }, k.label),
      el("div", { class: "value" }, fmt(k.value)),
      el("div", { class: "sub" }, k.sub, k.delta ? " · " : null, deltaSpan(k.delta)),
    ));
  }

  const events = (data.events || []).filter((e) => e.date >= todayKst).slice(0, 10);
  if (events.length) {
    const wd = ["일", "월", "화", "수", "목", "금", "토"];
    for (const e of events) {
      const d = new Date(`${e.date}T00:00:00Z`);
      const isToday = e.date === todayKst;
      const when = el("div", { class: "when" },
        isToday ? el("span", { class: "today" }, "오늘") : el("b", {}, `${d.getUTCMonth() + 1}.${d.getUTCDate()}`),
        ` (${wd[d.getUTCDay()]})`, e.time ? ` ${e.time}` : null);
      const title = e.url ? ext(e.url, e.title) : el("span", {}, e.title);
      title.classList.add("what");
      $("events").append(el("li", {}, when, el("div", {}, e.type ? el("span", { class: "chip" }, e.type) : null, title)));
    }
  } else {
    $("eventsSection").remove();
  }

  // ---------- 영상 카드 ----------
  const kstDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" });
  const ymd = (iso) => (iso ? kstDay.format(new Date(iso)).replaceAll("-", ".") : "");
  // 업로드 24시간 이내 = NEW, 7일 이내는 'N시간 전/N일 전'
  const NEW_HOURS = 24;
  const ageHours = (iso) => (iso ? (Date.now() - Date.parse(iso)) / 3600000 : Infinity);
  const isNew = (v) => ageHours(v.published_at) <= NEW_HOURS;
  function when(iso) {
    const h = ageHours(iso);
    if (h < 1) return "방금 전";
    if (h < 24) return `${Math.floor(h)}시간 전`;
    if (h < 24 * 7) return `${Math.floor(h / 24)}일 전`;
    return ymd(iso);
  }
  function videoCard(v, chipText, ...extra) {
    const fresh = isNew(v);
    return el("a", { class: `video${fresh ? " is-new" : ""}`, href: ytUrl(v.id), target: "_blank", rel: "noopener" },
      el("div", { class: "thumb" },
        el("img", { src: `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`, alt: "", loading: "lazy" }),
        fresh ? el("span", { class: "new" }, "NEW") : null,
        v.short ? el("span", { class: "badge" }, "쇼츠") : null),
      el("div", { class: "t" }, v.title),
      el("div", { class: "m" }, chipText ? el("span", { class: "chip" }, chipText) : null,
        el("span", { title: ymd(v.published_at), class: fresh ? "when-new" : "" }, when(v.published_at)),
        v.channel ? ` · ${v.channel}` : null),
      el("div", { class: "m" }, `조회수 ${fmt(v.views)}`, v.delta ? " · " : null, deltaSpan(v.delta)),
      ...extra,
    );
  }

  const newCount = data.videos.filter(isNew).length;
  if (newCount) $("recentHead").append(el("span", { class: "new-count" }, `NEW ${newCount}`));
  if (data.recent.length) {
    for (const v of data.recent) $("recent").append(videoCard(v, v.member || data.categories[v.category] || v.category));
  } else {
    $("recent").replaceWith(empty("아직 수집된 영상이 없어요"));
  }

  // ---------- MV ----------
  const goal = (f) => (f
    ? el("div", { class: "m goal", title: "최근 7일 평균 증가량 기준 예상" }, "다음 목표 ", el("b", {}, kr(f.target)), ` · 약 ${f.days}일 (하루 +${kr(f.rate)})`)
    : el("div", { class: "m goal" }, "다음 목표: 데이터 쌓는 중"));
  const mvs = [...data.mvs].sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  if (mvs.length) {
    for (const v of mvs) $("mvList").append(videoCard(v, null, goal(v.forecast)));
  } else {
    $("mvList").replaceWith(empty("등록된 MV가 없어요"));
  }

  // ---------- 멤버·직캠 ----------
  const dlg = $("memberDialog");
  $("dlgClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }); // 바깥 클릭으로 닫기
  function profile(m) {
    const facts = [m.ko, m.position, m.birth_year ? `${m.birth_year}년생` : "", m.nationality].filter(Boolean).join(" · ");
    const list = (label, items) => (items.length
      ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, label), el("ul", {}, ...items.map((x) => el("li", {}, x))))
      : null);
    return el("section", { class: "dlg-sec profile" },
      el("div", { class: "pf-facts" }, facts),
      m.nicknames.length ? el("div", { class: "pf-row" }, el("div", { class: "pf-label" }, "별명"), el("div", {}, m.nicknames.join(", "))) : null,
      list("데뷔 전", m.career),
      list("여담", m.notes),
      el("div", { class: "pf-src" }, "출처: ",
        ext(`https://namu.wiki/w/${encodeURIComponent(`${m.ko}(A2O SOUL)`)}`, "나무위키"), " 요약"));
  }

  function openMember(m, focus) {
    $("dlgTitle").textContent = m.name;
    const sections = [profile(m)];
    for (const [key, label, list] of [["fancams", "직캠", m.fancams], ["predebut", "데뷔 전", m.predebut]]) {
      if (!list.length) continue;
      sections.push(el("section", { class: "dlg-sec", id: `dlg-${key}` },
        el("h3", {}, `${label} ${list.length}개`),
        el("div", { class: "videos" }, ...list.map((v) => videoCard(v, null)))));
    }
    $("dlgBody").replaceChildren(...sections);
    dlg.showModal();
    dlg.scrollTop = 0;
    if (focus) $(`dlg-${focus}`)?.scrollIntoView();
  }

  // 멤버 탭: 공식 채널 + 프로필 카드
  for (const l of data.group_links || []) $("groupLinks").append(ext(l.url, l.label, " ↗"));
  if (!(data.group_links || []).length) $("groupLinks").closest("section").remove();
  for (const m of data.members) {
    const card = el("button", { class: "pcard", type: "button" },
      el("div", { class: "avatar", "aria-hidden": "true" }, m.ko ? m.ko[0] : m.name[0]),
      el("div", { class: "pinfo" },
        el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.ko)),
        el("div", { class: "s" }, [m.position, m.birth_year ? `${m.birth_year}년생` : "", m.nationality].filter(Boolean).join(" · ")),
        m.nicknames.length ? el("div", { class: "s" }, `별명 ${m.nicknames.join(", ")}`) : null,
        el("div", { class: "s more-link" }, "프로필 보기 ›")));
    card.addEventListener("click", () => openMember(m));
    $("profiles").append(card);
  }

  // 직캠 탭: 멤버별 최신 직캠
  for (const m of data.members) {
    const v = m.fancams[0] || m.predebut[0]; // 최신 직캠, 없으면 데뷔 전 영상
    const thumb = v
      ? el("img", { src: `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`, alt: "", loading: "lazy" })
      : el("div", { class: "nothumb" }, "직캠 집계 전");
    const links = [];
    if (m.fancams.length) links.push(["fancams", `직캠 ${m.fancams.length}`]);
    if (m.predebut.length) links.push(["predebut", `데뷔 전 ${m.predebut.length}`]);
    const body = [
      thumb,
      el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.position || m.nationality)),
      v ? el("div", { class: "t" }, v.title) : null,
      v ? el("div", { class: "s" }, `${ymd(v.published_at)} · 조회수 ${kr(v.views ?? 0)}`) : null,
      links.length ? el("div", { class: "s more-link" }, links.map((l) => l[1]).join(" · ") + " 보기 ›") : null,
    ];
    const card = el("button", { class: "member", type: "button" }, ...body);
    card.addEventListener("click", () => openMember(m, links[0]?.[0]));
    $("members").append(card);
  }

  // ---------- 전체 영상 ----------
  const CATS = [
    ["all", "전체", () => true],
    ["mv", "MV", (v) => v.category === "mv"],
    ["fancam", "직캠", (v) => v.category === "fancam"],
    ["content", "콘텐츠", (v) => v.category === "content" && !v.predebut],
    ["predebut", "데뷔 전", (v) => v.predebut],
  ];
  const FORMATS = [
    ["all", "전체", () => true],
    ["long", "롱폼", (v) => !v.short],
    ["short", "쇼츠", (v) => v.short],
  ];
  const PAGE = 24;
  const cur = { cat: "all", fmt: "all" };
  let shown = 0;
  const chipOf = (v) => (v.predebut ? "데뷔 전" : v.member || data.categories[v.category] || v.category);
  const pick = (defs, key) => defs.find((d) => d[0] === key)[2];
  const current = () => data.videos.filter((v) => pick(CATS, cur.cat)(v) && pick(FORMATS, cur.fmt)(v));
  function renderVideos(reset) {
    const list = current();
    if (reset) { $("allVideos").replaceChildren(); shown = 0; }
    $("allVideos").append(...list.slice(shown, shown + PAGE).map((v) => videoCard(v, chipOf(v))));
    shown = Math.min(shown + PAGE, list.length);
    $("more").hidden = shown >= list.length;
    if (!list.length) $("allVideos").append(empty("해당하는 영상이 없어요"));
  }
  function filterRow(defs, slot, countFn) {
    const row = el("div", { class: "filter-row" });
    const buttons = defs.map(([key, label]) => {
      const b = el("button", { type: "button", "data-key": key }, label);
      b.addEventListener("click", () => { cur[slot] = key; refresh(); });
      row.append(b);
      return b;
    });
    return { row, update: () => buttons.forEach((b) => {
      const key = b.dataset.key;
      b.classList.toggle("on", cur[slot] === key);
      b.textContent = `${defs.find((d) => d[0] === key)[1]} ${countFn(key)}`;
    }) };
  }
  const catRow = filterRow(CATS, "cat", (k) => data.videos.filter((v) => pick(CATS, k)(v) && pick(FORMATS, cur.fmt)(v)).length);
  const fmtRow = filterRow(FORMATS, "fmt", (k) => data.videos.filter((v) => pick(CATS, cur.cat)(v) && pick(FORMATS, k)(v)).length);
  $("filters").append(catRow.row, fmtRow.row);
  function refresh() { catRow.update(); fmtRow.update(); renderVideos(true); }
  $("more").addEventListener("click", () => renderVideos(false));
  refresh();

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
    if (!labels.length) { canvas.parentElement.replaceWith(empty("아직 수집된 데이터가 없어요")); return; }
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
    if (!labels.length) { canvas.parentElement.replaceWith(empty("이틀 이상 수집되면 표시돼요")); return; }
    new Chart(canvas, {
      type: "bar",
      data: { labels, datasets: diffs.map((d, i) => ({ label: d.name, data: labels.map((l) => d.out[l] ?? null),
                                                         backgroundColor: palette[i % palette.length], borderRadius: 4 })) },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                 scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: fmt } } }, plugins: { tooltip } },
    });
  }

  drawers.overview = () => lineChart("accountsChart", data.accounts);
  drawers.mv = () => { lineChart("mvChart", data.mvs); dailyChart("mvDailyChart", data.mvs); };

  showTab();
})();
