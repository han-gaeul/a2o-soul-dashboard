(async function () {
  const fmt = (v) => (v == null ? "–" : Number(v).toLocaleString("ko-KR"));
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs = {}, ...children) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else n.setAttribute(k, v);
    }
    for (const c of children) if (c != null) n.append(c);
    return n;
  };
  const deltaSpan = (d) => (d ? el("span", { class: "delta" }, `+${fmt(d)}`) : null);
  const ytUrl = (id) => `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;

  // 배포 시에는 ./data, 로컬 미리보기(레포 루트에서 서버 실행)에서는 ../data
  let data;
  for (const path of ["data/dashboard.json", "../data/dashboard.json"]) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (r.ok) { data = await r.json(); break; }
    } catch (_) { /* 다음 경로 시도 */ }
  }
  if (!data) { $("updated").textContent = "데이터를 불러오지 못했어요"; return; }

  // 헤더
  if (data.debut_date) {
    const todayKst = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date()); // YYYY-MM-DD
    const days = Math.round((Date.parse(todayKst) - Date.parse(data.debut_date)) / 86400000) + 1;
    $("dday").textContent = `D+${days}`;
    $("debut").textContent = `데뷔 ${data.debut_date.replaceAll("-", ".")}`;
  }
  $("updated").textContent = data.updated_at
    ? `마지막 수집: ${data.updated_at.slice(0, 16).replace("T", " ")} KST`
    : "아직 수집 전";

  // KPI
  for (const k of data.kpis) {
    $("kpis").append(el("div", { class: "card kpi" },
      el("div", { class: "label" }, k.label),
      el("div", { class: "value" }, fmt(k.value)),
      el("div", { class: "sub" }, k.sub, k.delta ? " · " : null, deltaSpan(k.delta)),
    ));
  }

  // 최신 영상
  if (data.recent.length) {
    for (const v of data.recent) {
      const chip = el("span", { class: "chip" }, v.member || data.categories[v.category] || v.category);
      $("recent").append(el("a", { class: "video", href: ytUrl(v.id), target: "_blank", rel: "noopener" },
        el("img", { src: `https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/mqdefault.jpg`, alt: "", loading: "lazy" }),
        el("div", { class: "t" }, v.title),
        el("div", { class: "m" }, chip, `조회수 ${fmt(v.views)}`, v.delta ? " · " : null, deltaSpan(v.delta)),
      ));
    }
  } else {
    $("recent").replaceWith(el("div", { class: "empty" }, "아직 수집된 영상이 없어요"));
  }

  // 표
  function table(headers, rows) {
    if (!rows.length) return el("div", { class: "empty" }, "데이터가 없어요");
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ...headers.map(([h, cls]) => el("th", cls ? { class: cls } : {}, h)))));
    const tb = el("tbody");
    for (const r of rows) tb.append(el("tr", {}, ...r.map(([v, cls]) => el("td", cls ? { class: cls } : {}, v))));
    t.append(tb);
    return t;
  }

  $("mvTable").append(table(
    [["영상"], ["조회수", "num"], ["증감", "num"]],
    data.mvs.map((v) => [
      [el("a", { href: ytUrl(v.id), target: "_blank", rel: "noopener" }, v.title)],
      [fmt(v.views), "num"],
      [deltaSpan(v.delta) || "", "num"],
    ]),
  ));

  if (data.fancam.length) {
    $("fancamTable").append(table(
      [["#"], ["멤버"], ["직캠 수", "num"], ["합계", "num"], ["증감", "num"]],
      data.fancam.map((r, i) => [[String(i + 1)], [r.member], [String(r.count), "num"], [fmt(r.views), "num"], [deltaSpan(r.delta) || "", "num"]]),
    ));
  } else {
    $("fancamSection").remove();
  }

  // 차트
  if (!window.Chart) return;
  const css = getComputedStyle(document.documentElement);
  Chart.defaults.color = css.getPropertyValue("--muted").trim();
  Chart.defaults.borderColor = css.getPropertyValue("--line").trim();
  Chart.defaults.font.family = "Pretendard, sans-serif";
  const palette = ["#6c4cf5", "#f5734c", "#12a1a0", "#e0479e", "#d4a017", "#3b82f6", "#8b5cf6", "#22c55e"];

  function lineChart(id, seriesList) {
    const canvas = $(id);
    const labels = [...new Set(seriesList.flatMap((s) => s.points.map((p) => p[0])))].sort();
    if (!labels.length) { canvas.parentElement.replaceWith(el("div", { class: "empty" }, "아직 수집된 데이터가 없어요")); return; }
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
      options: {
        maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { y: { ticks: { callback: fmt } } },
        plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}` } } },
      },
    });
  }
  lineChart("mvChart", data.mvs);
  lineChart("accountsChart", data.accounts);

  if (data.fancam.length) {
    $("fancamBox").style.height = `${60 + data.fancam.length * 32}px`;
    new Chart($("fancamChart"), {
      type: "bar",
      data: { labels: data.fancam.map((r) => r.member),
              datasets: [{ data: data.fancam.map((r) => r.views), backgroundColor: palette[0], borderRadius: 6 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } },
                 scales: { x: { ticks: { callback: fmt } } } },
    });
  }
})();
