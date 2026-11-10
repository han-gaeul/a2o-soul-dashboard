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
  const tabs = ["overview", "mv", "members"];
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
  const ymd = (iso) => (iso ? iso.slice(0, 10).replaceAll("-", ".") : "");
  function videoCard(v, chipText, ...extra) {
    return el("a", { class: "video", href: ytUrl(v.id), target: "_blank", rel: "noopener" },
      el("img", { src: `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`, alt: "", loading: "lazy" }),
      el("div", { class: "t" }, v.title),
      el("div", { class: "m" }, chipText ? el("span", { class: "chip" }, chipText) : null, ymd(v.published_at)),
      el("div", { class: "m" }, `조회수 ${fmt(v.views)}`, v.delta ? " · " : null, deltaSpan(v.delta)),
      ...extra,
    );
  }

  if (data.recent.length) {
    for (const v of data.recent) $("recent").append(videoCard(v, v.member || data.categories[v.category] || v.category));
  } else {
    $("recent").replaceWith(empty("아직 수집된 영상이 없어요"));
  }

  // ---------- MV ----------
  const goal = (f) => (f
    ? el("div", { class: "m goal" }, "다음 목표 ", el("b", {}, kr(f.target)), ` · 약 ${f.days}일 (하루 +${kr(f.rate)})`)
    : el("div", { class: "m goal" }, "다음 목표: 데이터 쌓는 중"));
  const mvs = [...data.mvs].sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  if (mvs.length) {
    for (const v of mvs) $("mvList").append(videoCard(v, null, goal(v.forecast)));
  } else {
    $("mvList").replaceWith(empty("등록된 MV가 없어요"));
  }

  // ---------- 멤버·직캠 ----------
  for (const m of data.members) {
    const v = m.latest;
    const thumb = v
      ? el("img", { src: `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`, alt: "", loading: "lazy" })
      : el("div", { class: "nothumb" }, "직캠 집계 전");
    const body = [
      thumb,
      el("div", { class: "n" }, m.name, el("span", { class: "c" }, m.nationality)),
      v ? el("div", { class: "t" }, v.title) : null,
      v ? el("div", { class: "s" }, `${v.published_at ? v.published_at.slice(0, 10).replaceAll("-", ".") + " · " : ""}조회수 ${kr(v.views ?? 0)}`) : null,
      m.fancam_count > 1 ? el("div", { class: "s" }, `직캠 ${m.fancam_count}개`) : null,
    ];
    $("members").append(v
      ? el("a", { class: "member", href: ytUrl(v.id), target: "_blank", rel: "noopener" }, ...body)
      : el("div", { class: "member" }, ...body));
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
