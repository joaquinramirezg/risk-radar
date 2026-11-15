// Render site/og.png and site/apple-touch-icon.png from card.html.
//   python3 -m http.server 8000 &   (from the repo root)
//   node tools/og/render.js
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.goto("http://localhost:8000/tools/og/card.html");
  await p.waitForSelector("body[data-ready]");
  await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: "site/og.png" });
  const i = await b.newPage({ viewport: { width: 180, height: 180 } });
  await i.goto("http://localhost:8000/tools/og/card.html");
  await i.evaluate(() => { document.body.innerHTML = document.querySelector(".mark").outerHTML; });
  await i.addStyleTag({ content: "body{width:180px;height:180px;background:#18202c} .mark{position:static;width:180px;height:180px;display:block}" });
  await i.screenshot({ path: "site/apple-touch-icon.png" });
  await b.close();
})();
