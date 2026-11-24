// 트윗 이미지 미리 만들기 → site/img/tw/
//   생일: bday_<영문이름>.jpg (멤버 15명, 그 멤버의 지금 프로필 사진 = 가장 최신 컨셉 포토)
//   MV 조회수: views_<영상id>_<숫자>.jpg (다음 돌파 단계 10개, 멤버 사진 모음)
// 멤버 프로필 사진(members.yml photo)을 새 컨셉 포토로 바꾸면 이걸 다시 돌리기 — 수집기가 health.md에 알려 줌
// 사용: node tools/make_tw_cards.js   (data/dashboard.json 필요, Playwright)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const R = path.resolve(__dirname, "..");
const OUT = path.join(R, "site/img/tw");
const dash = JSON.parse(fs.readFileSync(path.join(R, "data/dashboard.json"), "utf8"));
const siteFile = (rel) => {  // 한글 파일 이름 NFC/NFD 섞임 → 실제 파일 찾기
  const dir = path.join(R, "site", path.dirname(rel));
  const f = fs.readdirSync(dir).find((x) => x.normalize("NFC") === path.basename(rel).normalize("NFC"));
  return f ? "file://" + path.join(dir, f).split("/").map(encodeURIComponent).join("/").replace(/^file%3A/, "file:") : "";
};
const kr = (n) => (n >= 1e8 ? `${n / 1e8}억` : `${n / 1e4}만`);
const en = (n) => (n >= 1e9 ? `${n / 1e9}B` : n >= 1e6 ? `${n / 1e6}M` : `${n / 1e3}K`);
const MS = [1e5, 5e5, ...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((x) => x * 1e6), ...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((x) => x * 1e7),
  ...Array.from({ length: 20 }, (_, i) => (i + 1) * 1e8)];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 675 }, deviceScaleFactor: 1 });
  const base = "file://" + path.join(R, "tools/tw_card.html");
  const shot = async (qs, file) => {
    await p.goto(base + "?" + new URLSearchParams(qs).toString());
    await p.waitForTimeout(700);
    await p.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 88 });
  };
  const manifest = { photos: {}, made: new Date().toISOString().slice(0, 10) };
  for (const m of dash.members) {
    const [mm, dd] = (m.birthday || "").split("-");
    await shot({ kind: "bday", ko: m.ko, en: m.name, tag: m.name.replace(/[^A-Za-z0-9]/g, ""), date: `${mm}.${dd}`, img: siteFile(m.photo) }, `bday_${m.name}.jpg`);
    manifest.photos[m.name] = m.photo;
  }
  const imgs = dash.members.map((m) => siteFile(m.photo)).filter(Boolean).join("|");
  for (const v of dash.videos.filter((x) => x.category === "mv")) {
    const song = (v.title.match(/'([^']+)'/) || [])[1] || v.title;
    const label = /INFINITE/i.test(v.title) ? "INFINITE MV" : "Official MV";
    for (const n of MS.filter((x) => x > (v.views || 0)).slice(0, 10)) {
      await shot({ kind: "views", n: kr(n), en: en(n), song, label, imgs }, `views_${v.id}_${n}.jpg`);
    }
  }
  fs.writeFileSync(path.join(OUT, "cards.json"), JSON.stringify(manifest, null, 1) + "\n");
  await b.close();
  console.log("done", fs.readdirSync(OUT).length);
})();
